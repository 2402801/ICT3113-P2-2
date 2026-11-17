# Shared helpers for the A2 speed-test automation (P1 and P2). Dot-source it:
#   . "$PSScriptRoot\_a2common.ps1"
# Windows PowerShell 5.1 compatible. Builds on scripts\p1\_common.ps1 (paths, Ollama / compose helpers).
. "$PSScriptRoot\..\p1\_common.ps1"

$SpeedDir = Join-Path $RepoRoot 'datasets\a2\speed'
$ParamsPath = Join-Path $SpeedDir 'speed_params.json'
$WarmupPath = Join-Path $SpeedDir 'warmup_tickets.jsonl'
$ControlPort = 8099
$LargeModel = 'gemma4:e4b'

# The only things that change between configurations: which model answers first, and whether a cascade is on.
# (Ollama's own settings - parallelism, loaded models, keep-alive, threads, context - are never touched.)
# think: 'default' = Ollama's `think` flag is not sent, so gemma4 thinks as in A1 (the reference); 'false' = think=false is sent,
# and only gemma4 receives it (the service ignores the flag for the other models).
$A2Configs = [ordered]@{
    gemmaAlone        = @{ model = 'gemma4:e4b';   cascade = 'off'; think = 'default' }
    gemmaNoThink      = @{ model = 'gemma4:e4b';   cascade = 'off'; think = 'false' }
    mistralAlone      = @{ model = 'mistral:7b';   cascade = 'off'; think = 'default' }
    phi3Alone         = @{ model = 'phi3:3.8b';    cascade = 'off'; think = 'default' }
    llamaAlone        = @{ model = 'llama3.2:1b';  cascade = 'off'; think = 'default' }
    cascadeS1         = @{ model = 'phi3:3.8b';    cascade = 's1';  think = 'default' }
    cascadeS2         = @{ model = 'phi3:3.8b';    cascade = 's2';  think = 'default' }
    cascadeS1NoThink  = @{ model = 'phi3:3.8b';    cascade = 's1';  think = 'false' }   # optional: gemma4 answers without thinking
    cascadeS2NoThink  = @{ model = 'phi3:3.8b';    cascade = 's2';  think = 'false' }   # optional
}

function Get-SpeedRunId([string]$Config, [int]$Run) {
    '{0}_speed_{1}_run{2}' -f ($A2Configs[$Config].model -replace ':', '-'), $Config, $Run
}

function Read-Jsonl([string]$Path) {
    @(Get-Content -LiteralPath $Path -Encoding UTF8 | Where-Object { $_.Trim() } | ForEach-Object { ($_ | ConvertFrom-Json).narrative })
}

function Wait-Ollama([int]$TimeoutSec = 180) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ($true) {
        try { Get-OllamaVersion | Out-Null; return }
        catch {
            if ((Get-Date) -gt $deadline) { throw "Ollama not answering after $TimeoutSec s: $_" }
            Start-Sleep -Seconds 2
        }
    }
}

function Set-A2Config([string]$Name) {
    if (-not $A2Configs.Contains($Name)) { throw "Unknown configuration '$Name'. Known: $($A2Configs.Keys -join ', ')" }
    $c = $A2Configs[$Name]
    $models = New-Object System.Collections.Generic.List[string]
    $models.Add($c.model)
    if ($c.cascade -ne 'off') { $models.Add($LargeModel) }
    foreach ($m in $models) { Assert-PinnedDigest $m | Out-Null }
    Write-Step "Configuration $Name : model=$($c.model) cascade=$($c.cascade) think=$($c.think) (digests match the pins)"
    foreach ($pair in @(@('OLLAMA_MODEL', $c.model), @('CASCADE_SETTING', $c.cascade), @('CASCADE_LARGE_MODEL', $LargeModel), @('OLLAMA_THINK', $c.think))) {
        Set-DotEnvValue -Key $pair[0] -Value $pair[1]
        Set-Item -Path "Env:$($pair[0])" -Value $pair[1]   # a stale value in this shell would override .env
    }
    Write-Step 'Restarting the Ollama container (clears its prompt cache; no model is loaded afterwards)'
    Invoke-Compose @('restart', 'ollama') | Out-Null
    Wait-Ollama
    $loaded = @(Get-LoadedModels)
    if ($loaded.Count -ne 0) { throw "Models still resident after the restart: $($loaded.name -join ', ')" }
    Write-Ok 'Ollama restarted, nothing loaded'
    Write-Step 'Recreating the server container with the new configuration'
    Invoke-Compose @('up', '-d', '--no-deps', '--build', '--force-recreate', 'server') | Out-Null
    $h = Wait-Health
    if ($h.model -ne $c.model -or $h.cascade -ne $c.cascade -or $h.think -ne $c.think) {
        throw "Server reports model=$($h.model) cascade=$($h.cascade) think=$($h.think), expected model=$($c.model) cascade=$($c.cascade) think=$($c.think)"
    }
    Write-Ok "Server healthy: model=$($h.model) cascade=$($h.cascade) think=$($h.think)"
}

function Send-Ticket([string]$Narrative, [string]$RunId, [int]$TimeoutSec = 900) {
    $body = @{ narrative = $Narrative } | ConvertTo-Json
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $r = Invoke-WebRequest -UseBasicParsing -Method Post -Uri "$ApiUrl/tickets" -Body ([Text.Encoding]::UTF8.GetBytes($body)) `
        -ContentType 'application/json; charset=utf-8' -Headers @{ 'X-Run-Id' = $RunId } -TimeoutSec $TimeoutSec
    $sw.Stop()
    [pscustomobject]@{ seconds = $sw.Elapsed.TotalSeconds; req_id = "$($r.Headers['X-Request-ID'])"; body = ($r.Content | ConvertFrom-Json) }
}

function Get-LogFields([string]$ReqId) {
    # The service log line for one request, as a hashtable of its key=value fields (retries: the line may land a moment late).
    for ($i = 0; $i -lt 5; $i++) {
        $line = Select-String -Path $AccessLog -Pattern "req_id=$ReqId" -SimpleMatch -ErrorAction SilentlyContinue | Select-Object -Last 1
        if ($line) {
            $f = @{}
            foreach ($m in [regex]::Matches($line.Line, '(\w+)=("(?:[^"\\]|\\.)*"|\S+)')) { $f[$m.Groups[1].Value] = $m.Groups[2].Value.Trim('"') }
            return $f
        }
        Start-Sleep -Seconds 1
    }
    return @{}
}

function Invoke-Control([string]$Method, [string]$Path, $Body = $null) {
    $uri = "http://127.0.0.1:$ControlPort$Path"
    if ($Method -eq 'GET') { return Invoke-RestMethod -Uri $uri -TimeoutSec 5 }
    Invoke-RestMethod -Method Post -Uri $uri -Body ($Body | ConvertTo-Json -Depth 6) -ContentType 'application/json' -TimeoutSec 5
}

function Initialize-ControlServer {
    try { Invoke-Control GET '/state' | Out-Null; return } catch { }
    Write-Step "Starting the hand-shake server on port $ControlPort"
    $py = (Get-Command python -ErrorAction Stop).Source
    # Quote the script path: Windows PowerShell 5.1 joins -ArgumentList with spaces and does not quote, so a repo path
    # containing spaces would reach python split into several arguments.
    $server = '"{0}"' -f (Join-Path $PSScriptRoot 'control_server.py')
    Start-Process -FilePath $py -ArgumentList @('-I', $server, "$ControlPort") -WindowStyle Minimized | Out-Null
    for ($i = 0; $i -lt 15; $i++) {
        Start-Sleep -Seconds 1
        try { Invoke-Control GET '/state' | Out-Null; Write-Ok 'hand-shake server up'; return } catch { }
    }
    throw 'Hand-shake server did not start.'
}

function Get-LanIPv4List {
    @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -notmatch '^(127\.|169\.254\.)' } | ForEach-Object { $_.IPAddress })
}
