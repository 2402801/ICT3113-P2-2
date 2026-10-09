<#
.SYNOPSIS
  Puts the SUT into the official clean state for ONE run and prints READY for the tester
  (handoff Phase K steps 5-10 and Phase L).
.DESCRIPTION
  1. Checks the preconditions (service healthy, pinned model digest, committed code, native
     Ollama not running, power state recorded).
  2. Sends the fixed warm-up ticket(s) - not measured.
  3. Confirms the model is resident in RAM and CPU-only (size_vram = 0).
  4. Starts a fresh service log for the run (warm-up lines are kept separately).
  5. Truncates tickets + request_metrics and verifies both are 0.
  6. Creates runs\<run-id>\run_info.json and a READY row in runs\run_register.csv.
  Run ID format: <model>_<test-type>_<config>_run<n>, with ':' in the model tag written as '-'.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\p1\prepare_run.ps1 -TestType load -Config 1312tph -Run 1 -Tester P2
#>
param(
    [Parameter(Mandatory = $true)][ValidateSet('load', 'accuracy', 'stress', 'smoke')][string]$TestType,
    [Parameter(Mandatory = $true)][ValidatePattern('^[A-Za-z0-9.+-]+$')][string]$Config,
    [Parameter(Mandatory = $true)][ValidateRange(1, 99)][int]$Run,
    [Parameter(Mandatory = $true)][string]$Tester,
    [ValidateRange(1, 10)][int]$WarmupCount = 1,
    [string]$Notes = '',          # e.g. Legion thermal mode, network used, anything unusual
    [switch]$AllowDirty           # only for smoke/dev runs; official runs must be on a commit
)
. "$PSScriptRoot\_common.ps1"

Write-Step 'Checking preconditions'
$health = Wait-Health -TimeoutSec 30
$model = $health.model
$runId = '{0}_{1}_{2}_run{3}' -f ($model -replace ':', '-'), $TestType, $Config, $Run
$runDir = Join-Path $RunsDir $runId
if (Test-Path $runDir) { throw "$runDir already exists. Never overwrite evidence - use a new -Run number." }

$digest = Assert-PinnedDigest $model
Write-Ok "Model $model, digest $($digest.Substring(0, 12)) matches the pin"

$git = Get-GitInfo
if ($git.dirty -and -not $AllowDirty) {
    throw "Uncommitted changes outside runs/ and tests/environment/:`n$($git.dirty_files -join "`n")`nCommit first so this run maps to one exact commit."
}
Write-Ok "Git $($git.branch) @ $($git.commit.Substring(0, 12))$(if ($git.dirty) { ' (DIRTY - not official)' })"

if (Get-Process -Name 'ollama*' -ErrorAction SilentlyContinue) {
    throw 'Native Windows Ollama is running. Quit it from the system tray: it competes for CPU and can use the GPU.'
}
Write-Ok 'Native Windows Ollama is not running'

$power = Get-PowerState
if (-not $power.on_ac_power) { Write-Warn "On battery ($($power.battery_pct)%). Plug in AC for official runs." }
if ($power.power_mode -ne 'Best performance') { Write-Warn "Windows power mode is '$($power.power_mode)', official setting is 'Best performance'." }
if ($power.on_ac_power -and $power.power_mode -eq 'Best performance') { Write-Ok 'AC power, Best performance' }

Write-Step "Warm-up: $WarmupCount fixed ticket(s), not measured"
New-Item -ItemType Directory -Path $runDir | Out-Null
$warmupBody = @{ narrative = $WarmupNarrative } | ConvertTo-Json
for ($i = 1; $i -le $WarmupCount; $i++) {
    $r = Invoke-RestMethod -Method Post -Uri "$ApiUrl/tickets" -Body $warmupBody -ContentType 'application/json' `
        -Headers @{ 'X-Run-Id' = "$runId-warmup" } -TimeoutSec 900
    Write-Ok ("warm-up {0}: category='{1}' in {2:N0} ms" -f $i, $r.category, $r.classification_latency_ms)
}

Write-Step 'Checking the model is resident and CPU-only'
$loaded = @(Get-LoadedModels)
$entry = $loaded | Where-Object { $_.name -eq $model }
if (-not $entry) { throw "$model is not loaded in Ollama after the warm-up." }
if ($entry.size_vram -gt 0) { throw "$model reports $($entry.size_vram) bytes in VRAM: GPU use is forbidden. Do not run." }
Write-Utf8File -Path (Join-Path $runDir 'ollama_ps_before.json') -Content (ConvertTo-Json @($loaded) -Depth 6)
Write-Utf8File -Path (Join-Path $runDir 'ollama_ps_before.txt') -Content ((Invoke-Compose @('exec', '-T', 'ollama', 'ollama', 'ps')) -join "`n")
if ($loaded.Count -ne 1) { Write-Warn "$($loaded.Count) models resident; expected only $model" }
Write-Ok "$model loaded, size_vram=0 (CPU only)"

Write-Step 'Starting a fresh service log for this run'
Invoke-Compose @('stop', 'server') | Out-Null
if (Test-Path $AccessLog) { Move-Item -Path $AccessLog -Destination (Join-Path $runDir 'warmup_access.log') }
Invoke-Compose @('start', 'server') | Out-Null
Wait-Health | Out-Null
Write-Ok 'server restarted with an empty access.log (warm-up lines kept in warmup_access.log)'

Write-Step 'Resetting the database'
Invoke-MySql 'TRUNCATE TABLE request_metrics; TRUNCATE TABLE tickets;' | Out-Null
$counts = Get-DbCounts
if ($counts.tickets -ne 0 -or $counts.request_metrics -ne 0) {
    throw "Reset failed: tickets=$($counts.tickets) request_metrics=$($counts.request_metrics)"
}
Write-Ok 'tickets=0, request_metrics=0'

$ip = Get-LanIPv4
$readyAt = Get-UtcStamp
$info = [ordered]@{
    run_id          = $runId
    test_type       = $TestType
    config          = $Config
    run             = $Run
    tester          = $Tester
    model           = $model
    model_digest    = $digest
    prompt_version  = $health.prompt_version
    think           = $health.think
    ollama_version  = Get-OllamaVersion
    git_commit      = $git.commit
    git_branch      = $git.branch
    git_dirty       = $git.dirty
    on_ac_power     = $power.on_ac_power
    battery_pct     = $power.battery_pct
    power_mode      = $power.power_mode
    power_scheme    = $power.scheme
    warmup_count    = $WarmupCount
    sut_url         = "http://${ip}:8000"
    ready_at_utc    = $readyAt
    notes           = $Notes
}
Write-Utf8File -Path (Join-Path $runDir 'run_info.json') -Content (ConvertTo-Json $info -Depth 4)
Add-RegisterRow @{
    run_id = $runId; status = 'READY'; tester = $Tester; test_type = $TestType; config = $Config; run = $Run
    model = $model; model_digest = $digest; prompt_version = $health.prompt_version; think = $health.think
    ollama_version = $info.ollama_version; git_commit = $git.commit; git_dirty = $git.dirty
    on_ac_power = $power.on_ac_power; power_mode = $power.power_mode; ready_at_utc = $readyAt; notes = $Notes
}

Write-Host ''
Write-Host "READY  $runId" -ForegroundColor Green
Write-Host "  Tell $Tester to target  http://${ip}:8000   (check GET /health shows model=$model)"
Write-Host "  Optional request header  X-Run-Id: $runId   (stamped into every server log line)"
Write-Host "  When the tester is done:  scripts\p1\finish_run.ps1 -RunId $runId"
