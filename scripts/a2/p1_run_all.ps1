<#
.SYNOPSIS
  P1: run the whole A2 speed matrix unattended (P2 runs p2_run_loop.ps1 on the other laptop).
.DESCRIPTION
  Order is run-major (run 1 of every configuration, then run 2, ...), so slow drift on the laptop does not
  favour one configuration. Finished runs (runs\<id>\server_access.log exists) are skipped, so the script can be
  restarted after an interruption. It stops at the first failed run: fix the cause, delete that run's partial folder,
  start it again.
.EXAMPLE
  # default: the 9 required runs (gemmaAlone, cascadeS1, cascadeS2 x 3)
  powershell -ExecutionPolicy Bypass -File scripts\a2\p1_run_all.ps1
  # add a single model that passed the accuracy limits
  powershell -ExecutionPolicy Bypass -File scripts\a2\p1_run_all.ps1 -Configs gemmaAlone,cascadeS1,cascadeS2,mistralAlone
  # just show the plan
  powershell -ExecutionPolicy Bypass -File scripts\a2\p1_run_all.ps1 -PlanOnly
#>
param(
    # Default matrix: the brief's required configurations, 3 configurations x 3 runs = 9 runs.
    # The thinking-off configurations (gemmaNoThink, cascadeS1NoThink, cascadeS2NoThink) were dropped by the team; they stay
    # defined in _a2common.ps1 but must be requested explicitly with -Configs.
    [string[]]$Configs = @('gemmaAlone', 'cascadeS1', 'cascadeS2'),
    [ValidateRange(1, 9)][int]$Runs = 3,
    [string]$Tester = 'P2',
    [switch]$PlanOnly
)
. "$PSScriptRoot\_a2common.ps1"

$params = Get-Content $ParamsPath -Raw | ConvertFrom-Json
$perRunMin = ([int]$params.duration_sec + [int]$params.pause_sec) / 60 + 4
$plan = New-Object System.Collections.Generic.List[object]
for ($r = 1; $r -le $Runs; $r++) { foreach ($c in $Configs) { $plan.Add([pscustomobject]@{ Config = $c; Run = $r; Id = (Get-SpeedRunId $c $r) }) } }

Write-Step "Plan: $($plan.Count) runs, about $([math]::Round($plan.Count * $perRunMin / 60, 1)) hours in total"
$plan | ForEach-Object {
    $done = Test-Path (Join-Path (Join-Path $RunsDir $_.Id) 'server_access.log')
    Write-Host ("    {0,-45} {1}" -f $_.Id, $(if ($done) { 'done, will skip' } else { 'to do' }))
}
if ($PlanOnly) { return }

Write-Host ''
Write-Host 'P1 laptop IPv4 (give P2 the control URL):' -ForegroundColor Cyan
Get-LanIPv4List | ForEach-Object { Write-Host "    http://${_}:$ControlPort" }
Write-Host "  If P2 cannot reach it, allow the port once (admin PowerShell): New-NetFirewallRule -DisplayName 'A2 control' -Direction Inbound -Protocol TCP -LocalPort $ControlPort -Action Allow -Profile Any" -ForegroundColor DarkGray

Initialize-ControlServer
foreach ($item in $plan) {
    $dir = Join-Path $RunsDir $item.Id
    if (Test-Path (Join-Path $dir 'server_access.log')) { Write-Host "skip $($item.Id) (already finished)"; continue }
    if (Test-Path $dir) { throw "$dir exists but is not finished. If that run was aborted, delete the folder and start this script again." }
    Write-Host ''
    Write-Host "################ $($item.Id) ################" -ForegroundColor Magenta
    & (Join-Path $PSScriptRoot 'p1_speed_run.ps1') -Config $item.Config -Run $item.Run -Tester $Tester
}
Invoke-Control POST '/state' @{ state = 'FINISHED' } | Out-Null
Write-Host ''
Write-Host 'ALL RUNS COMPLETE. Commit the runs\ folders (P1 and P2 both), then hand over to P4.' -ForegroundColor Green
