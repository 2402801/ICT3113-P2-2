<#
.SYNOPSIS
  Test-set (88 even-row tickets) accuracy run of ANY A2 configuration, unattended - single models, thinking off, both cascades.
.DESCRIPTION
  switch configuration (restart Ollama, recreate server) -> prepare_run.ps1 (warm-up, residency check, clean log/DB)
  -> tests\accuracy\accuracy_test.py --golden datasets\a2\test_set.csv -> finish_run.ps1 -> sut_summary.json
  (escalation fraction from the log). Output: runs\<model>_accuracy_a2test88-<Config>_run<N>\.
  Run on the SUT laptop, with the SUT reachable at localhost. Commit scripts first (prepare_run refuses a dirty tree).
  Re-running after an interruption: delete the unfinished run folder, or pass a new -Run.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\a2\accuracy_run.ps1 -Config gemmaNoThink -Run 1
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\a2\accuracy_run.ps1 -Config cascadeS1 -Run 1 -Tester P3
#>
param(
    [Parameter(Mandatory = $true)][string]$Config,
    [ValidateRange(1, 99)][int]$Run = 1,
    [string]$Tester = 'P3',
    [string]$Notes = ''
)
. "$PSScriptRoot\_a2common.ps1"

$cfg = $A2Configs[$Config]
if (-not $cfg) { throw "Unknown configuration '$Config'. Known: $($A2Configs.Keys -join ', ')" }
$label = "a2test88-$Config"
$runId = '{0}_accuracy_{1}_run{2}' -f ($cfg.model -replace ':', '-'), $label, $Run
$runDir = Join-Path $RunsDir $runId
if (Test-Path $runDir) { throw "$runDir already exists. Never overwrite evidence; use a new -Run number or delete an unfinished folder." }

Set-A2Config $Config
$required = @()
if ($cfg.cascade -ne 'off') { $required = @($LargeModel) }
$prep = @{ TestType = 'accuracy'; Config = $label; Run = $Run; Tester = $Tester; RequireModels = $required; Notes = $Notes }
if (Test-Path $WarmupPath) { $prep.WarmupFile = $WarmupPath }   # the same 3 warm-ups as the speed runs, once setup_speed.ps1 has chosen them
& (Join-Path $PSScriptRoot '..\p1\prepare_run.ps1') @prep

$py = (Get-Command python -ErrorAction Stop).Source
Write-Step "Scoring the 88 test-set tickets through POST /tickets ($runId)"
& $py (Join-Path $RepoRoot 'tests\accuracy\accuracy_test.py') --run-id $runId --out-dir $runDir --golden (Join-Path $RepoRoot 'datasets\a2\test_set.csv') | Out-Host
if ($LASTEXITCODE -ne 0) { throw "accuracy_test.py failed (exit $LASTEXITCODE). Delete $runDir and run again." }

& (Join-Path $PSScriptRoot '..\p1\finish_run.ps1') -RunId $runId -Notes $Notes
& $py -I (Join-Path $PSScriptRoot 'run_summary.py') --run-dir $runDir --out (Join-Path $runDir 'sut_summary.json') | Out-Host
Write-Host ''
Write-Host "ACCURACY RUN COMPLETE $runId" -ForegroundColor Green
Write-Host 'Next: P3 scores it (analysis\a2_accuracy.py) against the limits; commit the runs\ folder.'
