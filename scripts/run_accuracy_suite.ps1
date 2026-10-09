<#
.SYNOPSIS
  Runs the official golden-set accuracy runs for every candidate model, unattended.
.DESCRIPTION
  For each model: scripts\p1\switch_model.ps1 once, then for each run number:
    scripts\p1\prepare_run.ps1 -TestType accuracy  ->  accuracy\accuracy_test.py  ->  scripts\p1\finish_run.ps1
  The accuracy CSV and .meta.json are written straight into runs\<run-id>\, so nothing needs copying.
  At the end it runs analysis\reconcile.py and accuracy\accuracy_report.py.
  The full test procedure is in docs\ACCURACY_PLAYBOOK.md.

  Safe to re-run after a crash or Ctrl+C: finished runs are skipped, and a run that was prepared but
  not finished is resumed (accuracy_test.py --resume) and then finished.
  Commit this script before using it: prepare_run.ps1 refuses to start on uncommitted changes.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\run_accuracy_suite.ps1 -Tester P3
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\run_accuracy_suite.ps1 -Tester P3 -Models phi3:3.8b -Runs 2,3
#>
param(
    [Parameter(Mandatory = $true)][string]$Tester,
    [string[]]$Models = @('llama3.2:1b', 'phi3:3.8b', 'mistral:7b', 'gemma4:e4b'),
    [int[]]$Runs = @(1, 2, 3),
    [string]$Config = 'golden175',
    [string]$Python = ''   # path to a Python 3.10+ interpreter; found automatically when omitted
)
$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$P1 = Join-Path $PSScriptRoot 'p1'
$AccuracyTest = Join-Path $RepoRoot 'accuracy\accuracy_test.py'
$AccuracyReport = Join-Path $RepoRoot 'accuracy\accuracy_report.py'

function Find-Python {
    # "python" on Windows is often the Microsoft Store stub, which exits without running anything.
    $candidates = @('python', 'py', (Join-Path $env:USERPROFILE 'anaconda3\python.exe'),
        (Join-Path $env:USERPROFILE 'miniconda3\python.exe'))
    foreach ($c in $candidates) {
        try {
            $v = & $c -c 'import sys; print(sys.version_info >= (3, 10))' 2>$null
            if ($LASTEXITCODE -eq 0 -and "$v".Trim() -eq 'True') { return $c }
        }
        catch { }
    }
    throw 'No Python 3.10+ found. Pass -Python C:\path\to\python.exe'
}

function Invoke-Python([string[]]$Arguments) {
    # Out-Host: show Python's output live instead of returning it with the exit code.
    & $Python @Arguments | Out-Host
    return $LASTEXITCODE
}

function Get-NoAnswerCount([string]$CsvPath) {
    # Tickets whose latest attempt got no HTTP answer (status 0); accuracy_test.py --resume retries exactly these.
    $latest = @{}
    Import-Csv -Path $CsvPath -Encoding UTF8 | ForEach-Object { $latest[$_.row] = $_.status }
    return @($latest.Values | Where-Object { $_ -eq '0' }).Count
}

if (-not $Python) { $Python = Find-Python }
Write-Host "Python: $Python" -ForegroundColor Cyan
$suiteStart = Get-Date
$done = @()

foreach ($model in $Models) {
    $prefix = '{0}_accuracy_{1}' -f ($model -replace ':', '-'), $Config
    $pending = @($Runs | Where-Object { -not (Test-Path (Join-Path $RepoRoot "runs\${prefix}_run$_\server_access.log")) })
    if ($pending.Count -eq 0) {
        Write-Host "`n### $model : runs $($Runs -join ', ') already finished - skipped" -ForegroundColor DarkGray
        $done += $Runs | ForEach-Object { "${prefix}_run$_" }
        continue
    }

    Write-Host "`n### $model" -ForegroundColor Magenta
    & (Join-Path $P1 'switch_model.ps1') -Model $model

    foreach ($n in $Runs) {
        $runId = "${prefix}_run$n"
        $runDir = Join-Path $RepoRoot "runs\$runId"
        if (Test-Path (Join-Path $runDir 'server_access.log')) {
            Write-Host "`n--- $runId already finished - skipped" -ForegroundColor DarkGray
            $done += $runId
            continue
        }
        $runStart = Get-Date
        $csv = Join-Path $runDir "${runId}_accuracy.csv"
        $testArgs = @($AccuracyTest, '--run-id', $runId, '--out-dir', $runDir)
        if (Test-Path (Join-Path $runDir 'run_info.json')) {
            # Prepared earlier but never finished (crash / Ctrl+C): continue the same run.
            Write-Host "`n--- $runId was interrupted - resuming it" -ForegroundColor Yellow
            if (Test-Path $csv) { $testArgs += '--resume' }
        }
        else {
            Write-Host "`n--- $runId : prepare" -ForegroundColor Cyan
            & (Join-Path $P1 'prepare_run.ps1') -TestType accuracy -Config $Config -Run $n -Tester $Tester
        }

        Write-Host "--- $runId : 175 golden tickets" -ForegroundColor Cyan
        $code = Invoke-Python $testArgs
        if ($code -ne 0) { throw "accuracy_test.py failed for $runId (exit $code). Fix it, then re-run this script to resume." }
        if ((Test-Path $csv) -and (Get-NoAnswerCount $csv) -gt 0) {
            Write-Host "--- $runId : retrying tickets that got no HTTP answer" -ForegroundColor Yellow
            $code = Invoke-Python (@($testArgs | Where-Object { $_ -ne '--resume' }) + '--resume')
            if ($code -ne 0) { throw "accuracy_test.py --resume failed for $runId (exit $code)." }
        }

        Write-Host "--- $runId : finish" -ForegroundColor Cyan
        & (Join-Path $P1 'finish_run.ps1') -RunId $runId
        $done += $runId
        Write-Host ("--- $runId done in {0:N1} min" -f ((Get-Date) - $runStart).TotalMinutes) -ForegroundColor Green
    }
}

Write-Host ("`n### All accuracy runs finished in {0:N1} h" -f ((Get-Date) - $suiteStart).TotalHours) -ForegroundColor Green
Push-Location (Join-Path $RepoRoot 'analysis')
try {
    Write-Host "`n### Reconciliation" -ForegroundColor Magenta
    $code = Invoke-Python (@('reconcile.py') + $done)
    if ($code -ne 0) { Write-Host '!! Some runs failed reconciliation - read the output above before reporting.' -ForegroundColor Red }
    Write-Host "`n### Accuracy report" -ForegroundColor Magenta
    $null = Invoke-Python (@($AccuracyReport) + $done)
}
finally { Pop-Location }
Write-Host "`nReport: analysis\output\accuracy_report.md"
Write-Host 'Commit the runs\ folders so every reported number stays traceable.'
