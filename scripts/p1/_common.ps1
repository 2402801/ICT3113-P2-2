# Shared helpers for the P1 (SUT / infrastructure) scripts. Dot-source it:
#   . "$PSScriptRoot\_common.ps1"
# Windows PowerShell 5.1 compatible. Paths are resolved from the repo root, so the scripts can be
# run from any working directory.

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$ComposeFile = Join-Path $RepoRoot 'docker-compose.yml'
$RunsDir = Join-Path $RepoRoot 'runs'
$RegisterPath = Join-Path $RunsDir 'run_register.csv'
$EnvDocDir = Join-Path $RepoRoot 'docs\environment'
$PinsPath = Join-Path $EnvDocDir 'model_pins.json'
$AccessLog = Join-Path $RepoRoot 'server\logs\access.log'
$ApiUrl = 'http://localhost:8000'
$OllamaUrl = 'http://localhost:11434'

# Frozen candidate set from Step 4, with the short model IDs recorded in that document.
$Candidates = @('llama3.2:1b', 'phi3:3.8b', 'mistral:7b', 'gemma4:e4b')
$Step4ShortIds = @{
    'llama3.2:1b' = 'baf6a787fdff'
    'phi3:3.8b'   = '4f2222927938'
    'mistral:7b'  = '6577803aa9a0'
    'gemma4:e4b'  = 'c6eb396dbd59'
}

# Fixed warm-up ticket. It is invented text, so no dataset or golden-set ticket is ever used to warm up.
$WarmupNarrative = 'I was charged a late fee on my credit card even though I paid before the due date, and the card issuer refuses to refund it.'

$RegisterColumns = @(
    'run_id', 'status', 'tester', 'test_type', 'config', 'run', 'model', 'model_digest',
    'prompt_version', 'think', 'ollama_version', 'git_commit', 'git_dirty', 'on_ac_power',
    'power_mode', 'ready_at_utc', 'finished_at_utc', 'server_log', 'notes'
)

function Write-Step([string]$Message) { Write-Host "==> $Message" -ForegroundColor Cyan }
function Write-Ok([string]$Message) { Write-Host "    OK  $Message" -ForegroundColor Green }
function Write-Warn([string]$Message) { Write-Host "    !!  $Message" -ForegroundColor Yellow }

function Get-UtcStamp { (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ') }

function Write-Utf8File([string]$Path, [string]$Content) {
    # UTF-8 without BOM (PowerShell 5.1's -Encoding utf8 adds a BOM, which breaks .env parsing).
    [System.IO.File]::WriteAllText($Path, $Content, (New-Object System.Text.UTF8Encoding $false))
}

function Invoke-Native {
    # Runs a native command, returns its output lines, and throws on a non-zero exit code.
    param([string]$Exe, [string[]]$Arguments, [switch]$AllowFail)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { $output = @(& $Exe @Arguments 2>&1 | ForEach-Object { "$_" }) }
    finally { $ErrorActionPreference = $previous }
    if (-not $AllowFail -and $LASTEXITCODE -ne 0) {
        throw "$Exe $($Arguments -join ' ') failed (exit $LASTEXITCODE):`n$($output -join "`n")"
    }
    return $output
}

function Invoke-Compose([string[]]$Arguments, [switch]$AllowFail) {
    Invoke-Native -Exe 'docker' -Arguments (@('compose', '-f', $ComposeFile) + $Arguments) -AllowFail:$AllowFail
}

function Invoke-MySql([string]$Sql) {
    # MYSQL_PWD avoids the "password on the command line" warning polluting the output.
    Invoke-Compose @('exec', '-T', '-e', 'MYSQL_PWD=triage', 'mysql', 'mysql', '-utriage', 'triage', '--batch', '-N', '-e', $Sql)
}

function Get-DbCounts {
    $values = (Invoke-MySql 'SELECT (SELECT COUNT(*) FROM tickets), (SELECT COUNT(*) FROM request_metrics);' |
            Select-Object -Last 1) -split "`t"
    [pscustomobject]@{ tickets = [int]$values[0]; request_metrics = [int]$values[1] }
}

function Export-Table([string]$Table, [string]$Destination) {
    # Dump inside the container, then docker cp the bytes out, so PowerShell never re-encodes them.
    Invoke-Compose @('exec', '-T', '-e', 'MYSQL_PWD=triage', 'mysql', 'sh', '-c',
        "mysql -utriage triage --batch -e 'SELECT * FROM $Table ORDER BY id' > /tmp/$Table.tsv") | Out-Null
    $container = (Invoke-Compose @('ps', '-q', 'mysql') | Select-Object -First 1).Trim()
    Invoke-Native -Exe 'docker' -Arguments @('cp', "${container}:/tmp/$Table.tsv", $Destination) | Out-Null
}

function Get-Health([int]$TimeoutSec = 5) {
    Invoke-RestMethod -Uri "$ApiUrl/health" -TimeoutSec $TimeoutSec
}

function Wait-Health([int]$TimeoutSec = 180) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ($true) {
        try { return Get-Health }
        catch {
            if ((Get-Date) -gt $deadline) { throw "Triage service not healthy after $TimeoutSec s: $_" }
            Start-Sleep -Seconds 2
        }
    }
}

function Get-OllamaVersion { (Invoke-RestMethod -Uri "$OllamaUrl/api/version" -TimeoutSec 10).version }

function Get-ModelInventory {
    # Every model in the Docker Ollama store, with its full manifest digest from the Ollama API.
    @((Invoke-RestMethod -Uri "$OllamaUrl/api/tags" -TimeoutSec 10).models) | Where-Object { $_ } | ForEach-Object {
        $digest = $_.digest -replace '^sha256:', ''
        [pscustomobject]@{
            tag            = $_.name
            digest         = $digest
            short_id       = $digest.Substring(0, 12)
            size_bytes     = $_.size
            parameter_size = $_.details.parameter_size
            quantization   = $_.details.quantization_level
            family         = $_.details.family
            step4_short_id = $Step4ShortIds[$_.name]
        }
    }
}

function Get-LoadedModels {
    # Models resident in RAM. size_vram > 0 would mean GPU offload, which the brief forbids.
    @((Invoke-RestMethod -Uri "$OllamaUrl/api/ps" -TimeoutSec 10).models) | Where-Object { $_ }
}

function Get-PinnedDigest([string]$Model) {
    if (-not (Test-Path $PinsPath)) { return $null }
    $pin = @(Get-Content $PinsPath -Raw | ConvertFrom-Json) | Where-Object { $_.tag -eq $Model }
    if ($pin) { return $pin.digest }
    return $null
}

function Assert-PinnedDigest([string]$Model) {
    $current = Get-ModelInventory | Where-Object { $_.tag -eq $Model }
    if (-not $current) { throw "$Model is not pulled into Docker Ollama (scripts\p1\pin_models.ps1 -Pull)." }
    $pinned = Get-PinnedDigest $Model
    if (-not $pinned) { throw "$Model has no pinned digest in docs\environment\model_pins.json (run scripts\p1\pin_models.ps1)." }
    if ($current.digest -ne $pinned) {
        throw "$Model digest changed: pinned $pinned, now $($current.digest). Results would not be comparable."
    }
    return $current.digest
}

function Set-DotEnvValue([string]$Key, [string]$Value) {
    $path = Join-Path $RepoRoot '.env'
    $lines = @()
    if (Test-Path $path) { $lines = @(Get-Content $path | Where-Object { $_ -notmatch "^\s*$Key\s*=" }) }
    $lines += "$Key=$Value"
    Write-Utf8File -Path $path -Content (($lines -join "`n") + "`n")
}

function Get-GitInfo {
    $commit = Invoke-Native -Exe 'git' -Arguments @('-C', $RepoRoot, 'rev-parse', 'HEAD') | Select-Object -First 1
    $branch = Invoke-Native -Exe 'git' -Arguments @('-C', $RepoRoot, 'rev-parse', '--abbrev-ref', 'HEAD') | Select-Object -First 1
    # Evidence folders change during runs by design, so they do not count as a dirty tree.
    $dirty = @(Invoke-Native -Exe 'git' -Arguments @('-C', $RepoRoot, 'status', '--porcelain', '--',
            '.', ':(exclude)runs', ':(exclude)docs/environment') | Where-Object { $_ })
    [pscustomobject]@{ commit = $commit; branch = $branch; dirty = ($dirty.Count -gt 0); dirty_files = $dirty }
}

function Get-PowerState {
    Add-Type -AssemblyName System.Windows.Forms
    $status = [System.Windows.Forms.SystemInformation]::PowerStatus
    $onAc = ($status.PowerLineStatus -eq 'Online')
    $key = Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Power\User\PowerSchemes' -ErrorAction SilentlyContinue
    $overlay = $null
    if ($key) {
        if ($onAc) { $overlay = $key.ActiveOverlayAcPowerScheme } else { $overlay = $key.ActiveOverlayDcPowerScheme }
    }
    $modes = @{
        'ded574b5-45a0-4f42-8737-46345c09c238' = 'Best performance'
        '00000000-0000-0000-0000-000000000000' = 'Balanced'
        '961cc777-2547-4f9d-8174-7d86181b8a7a' = 'Best power efficiency'
    }
    $mode = 'unknown'
    if ($overlay -and $modes.ContainsKey($overlay)) { $mode = $modes[$overlay] }
    [pscustomobject]@{
        on_ac_power = $onAc
        battery_pct = [math]::Round($status.BatteryLifePercent * 100)
        power_mode  = $mode
        scheme      = ((powercfg /getactivescheme) -join ' ').Trim()
    }
}

function Get-LanIPv4 {
    $cfg = Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up' } |
        Select-Object -First 1
    if ($cfg) { return ($cfg.IPv4Address | Select-Object -First 1).IPAddress }
    return $null
}

function Read-Register {
    if (Test-Path $RegisterPath) { return @(Import-Csv -Path $RegisterPath) }
    return @()
}

function Write-Register($Rows) {
    New-Item -ItemType Directory -Force -Path $RunsDir | Out-Null
    @($Rows) | Select-Object $RegisterColumns | Export-Csv -Path $RegisterPath -NoTypeInformation -Encoding UTF8
}

function Add-RegisterRow([hashtable]$Row) {
    Write-Register (@(Read-Register) + @([pscustomobject]$Row))
}

function Update-RegisterRow([string]$RunId, [hashtable]$Changes) {
    $rows = @(Read-Register)
    $match = $rows | Where-Object { $_.run_id -eq $RunId }
    if (-not $match) { throw "Run $RunId is not in $RegisterPath" }
    foreach ($key in $Changes.Keys) { $match.$key = $Changes[$key] }
    Write-Register $rows
}
