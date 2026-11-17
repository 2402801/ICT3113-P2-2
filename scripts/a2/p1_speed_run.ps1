<#
.SYNOPSIS
  P1: one fully automated A2 speed run (one configuration, one run number).
.DESCRIPTION
  switch configuration -> restart Ollama -> recreate server -> 3 fixed warm-ups -> check the right models are resident
  (both, for a cascade) -> clean log and database -> GET /stats -> tell P2 "READY" -> wait for P2's JMeter to finish
  -> GET /stats -> finish_run.ps1 (archives log, DB rows, ollama log, ollama ps) -> write sut_summary.json
  (escalation fraction from the log, stats delta).
  P2 must be running scripts\a2\p2_run_loop.ps1. Needs a clean git tree outside runs\ and tests\environment\.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\a2\p1_speed_run.ps1 -Config cascadeS1 -Run 1
#>
param(
    [Parameter(Mandatory = $true)][string]$Config,
    [Parameter(Mandatory = $true)][ValidateRange(1, 99)][int]$Run,
    [string]$Tester = 'P2',
    [string]$Notes = ''
)
. "$PSScriptRoot\_a2common.ps1"

if (-not (Test-Path $ParamsPath)) { throw "No speed_params.json. Run scripts\a2\setup_speed.ps1 first." }
if (-not (Test-Path $WarmupPath)) { throw "No warmup_tickets.jsonl. Run scripts\a2\setup_speed.ps1 first." }
$params = Get-Content $ParamsPath -Raw | ConvertFrom-Json
$cfg = $A2Configs[$Config]
if (-not $cfg) { throw "Unknown configuration '$Config'. Known: $($A2Configs.Keys -join ', ')" }
$runId = Get-SpeedRunId $Config $Run
$runDir = Join-Path $RunsDir $runId
if (Test-Path $runDir) { throw "$runDir already exists. Delete the partial folder if that run was aborted; never overwrite evidence." }

Initialize-ControlServer
Invoke-Control POST '/state' @{ state = 'IDLE' } | Out-Null

Set-A2Config $Config

$required = @()
if ($cfg.cascade -ne 'off') { $required = @($LargeModel) }
& (Join-Path $PSScriptRoot '..\p1\prepare_run.ps1') -TestType speed -Config $Config -Run $Run -Tester $Tester `
    -WarmupFile $WarmupPath -RequireModels $required -Notes $Notes

Write-Step 'GET /stats before the run'
$before = Invoke-RestMethod -Uri "$ApiUrl/stats" -TimeoutSec 10
Write-Utf8File -Path (Join-Path $runDir 'stats_before.json') -Content (ConvertTo-Json $before -Depth 4)
Write-Ok "total before = $($before.total)"

$state = @{
    state = 'READY'; run_id = $runId; config = $Config; run = $Run
    model = $cfg.model; cascade = $cfg.cascade
    rate_per_hour = [int]$params.rate_per_hour; duration_sec = [int]$params.duration_sec
    pause_sec = [int]$params.pause_sec; response_timeout_ms = [int]$params.response_timeout_sec * 1000
    random_seed = 1000 + $Run; ready_at_utc = (Get-UtcStamp)
}
Invoke-Control POST '/state' $state | Out-Null
Write-Host ''
Write-Host "READY $runId - waiting for P2's JMeter (about $([math]::Round(([int]$params.duration_sec + [int]$params.pause_sec) / 60, 1)) min)..." -ForegroundColor Green

$limitSec = [int]$params.duration_sec + [int]$params.pause_sec + 900
$started = Get-Date
$nextNote = 60
try {
    while ($true) {
        $st = Invoke-Control GET '/state'
        if ($st.done) { break }
        $elapsed = ((Get-Date) - $started).TotalSeconds
        if ($elapsed -gt $limitSec) { throw "P2 did not report DONE within $limitSec s. Check P2's window; this run is not valid." }
        if ($elapsed -ge $nextNote) {
            $n = (Select-String -Path $AccessLog -Pattern ' POST /tickets ' -SimpleMatch -ErrorAction SilentlyContinue | Measure-Object).Count
            Write-Host ("    {0,5:N0} s elapsed, {1} POST /tickets logged so far" -f $elapsed, $n)
            $nextNote += 60
        }
        Start-Sleep -Seconds 5
    }
}
catch {
    try { Invoke-Control POST '/state' @{ state = 'IDLE' } | Out-Null } catch { }
    throw
}
Write-Ok "P2 reported DONE: $(($st.result | ConvertTo-Json -Compress))"
Start-Sleep -Seconds 15

Write-Step 'GET /stats after the run'
$after = Invoke-RestMethod -Uri "$ApiUrl/stats" -TimeoutSec 10
Write-Utf8File -Path (Join-Path $runDir 'stats_after.json') -Content (ConvertTo-Json $after -Depth 4)
Write-Ok "total after = $($after.total)  (completed and stored = $($after.total - $before.total))"
Write-Utf8File -Path (Join-Path $runDir 'p2_report.json') -Content (ConvertTo-Json $st.result -Depth 4)

& (Join-Path $PSScriptRoot '..\p1\finish_run.ps1') -RunId $runId -Notes $Notes
Invoke-Control POST '/state' @{ state = 'IDLE' } | Out-Null

Write-Step 'Writing sut_summary.json (escalation fraction from the service log)'
$py = (Get-Command python -ErrorAction Stop).Source
& $py -I (Join-Path $PSScriptRoot 'run_summary.py') --run-dir $runDir --out (Join-Path $runDir 'sut_summary.json')
Write-Host ''
Write-Host "RUN COMPLETE $runId" -ForegroundColor Green
