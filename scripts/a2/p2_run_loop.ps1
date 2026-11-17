<#
.SYNOPSIS
  P2: unattended JMeter driver for the A2 speed runs, on the separate load-generator laptop.
.DESCRIPTION
  Polls P1's hand-shake server. When P1 publishes a READY run, checks the SUT /health matches the configuration,
  runs JMeter (tests\load\speed_test.jmx) with the committed workload and the agreed rate / duration / timeout / pause,
  saves runs\<run-id>\<run-id>.jtl, writes client_summary.json, and reports DONE. Leave it running for the whole matrix;
  it exits when P1 announces FINISHED.
  The load generator must NOT run on the SUT laptop.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\a2\p2_run_loop.ps1 -ControlUrl http://192.168.1.20:8099
#>
param(
    [Parameter(Mandatory = $true)][string]$ControlUrl,       # P1's laptop, e.g. http://192.168.1.20:8099
    [string]$SutHost = '',                                    # defaults to the host in ControlUrl
    [int]$SutPort = 8000,
    [string]$JMeter = 'C:\Users\natli\tools\apache-jmeter-5.6.3\bin\jmeter.bat',
    [switch]$Once,                                            # handle one run then exit
    [switch]$NoEarlyFinish                                    # always wait for the full drain pause
)
$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$RunsDir = Join-Path $RepoRoot 'runs'
$Plan = Join-Path $RepoRoot 'tests\load\speed_test.jmx'
$Workload = Join-Path $RepoRoot 'datasets\a2\speed\workload_tickets.jsonl'
$Summary = Join-Path $PSScriptRoot 'run_summary.py'
if (-not $SutHost) { $SutHost = ([uri]$ControlUrl).Host }
if (-not (Test-Path $JMeter)) { $c = Get-Command jmeter -ErrorAction SilentlyContinue; if ($c) { $JMeter = $c.Source } else { throw "JMeter not found at $JMeter. Pass -JMeter <path to jmeter.bat>." } }
foreach ($p in $Plan, $Workload) { if (-not (Test-Path $p)) { throw "Missing $p (git pull the committed files)." } }
$py = (Get-Command python -ErrorAction Stop).Source

Write-Host "P2 loop: control $ControlUrl, SUT ${SutHost}:$SutPort, JMeter $JMeter" -ForegroundColor Cyan
$handled = @{}
while ($true) {
    try { $s = Invoke-RestMethod -Uri "$ControlUrl/state" -TimeoutSec 8 }
    catch { Write-Host "  (cannot reach $ControlUrl yet: $($_.Exception.Message))" -ForegroundColor DarkGray; Start-Sleep -Seconds 10; continue }

    if ($s.state -eq 'FINISHED') { Write-Host 'P1 says ALL RUNS COMPLETE. Commit runs\ and stop.' -ForegroundColor Green; break }
    if ($s.state -ne 'READY' -or $s.done -or $handled.ContainsKey($s.run_id)) { Start-Sleep -Seconds 5; continue }

    $runId = $s.run_id
    $handled[$runId] = $true
    Write-Host ''
    Write-Host "################ $runId  ($($s.rate_per_hour)/hour for $($s.duration_sec) s, pause $($s.pause_sec) s) ################" -ForegroundColor Magenta

    $h = Invoke-RestMethod -Uri "http://${SutHost}:$SutPort/health" -TimeoutSec 15
    if ($h.model -ne $s.model -or $h.cascade -ne $s.cascade) {
        throw "SUT /health says model=$($h.model) cascade=$($h.cascade) but the run needs model=$($s.model) cascade=$($s.cascade). Not running."
    }
    $dir = Join-Path $RunsDir $runId
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $jtl = Join-Path $dir "$runId.jtl"
    if (Test-Path $jtl) { throw "$jtl already exists; never overwrite evidence." }

    $jargs = @(
        '-n', '-t', $Plan, '-j', (Join-Path $dir 'jmeter.log'),
        "-Jhost=$SutHost", "-Jport=$SutPort", "-Jrun_id=$runId",
        "-Jdata_file=$Workload", "-Jjtl=$jtl", '-Jsample_variables=req_id',
        "-Jrate_per_hour=$($s.rate_per_hour)", "-Jduration_sec=$($s.duration_sec)", "-Jpause_sec=$($s.pause_sec)",
        "-Jresponse_timeout_ms=$($s.response_timeout_ms)", "-Jrandom_seed=$($s.random_seed)"
    )
    $t0 = Get-Date
    Write-Host "  JMeter started $($t0.ToString('HH:mm:ss'))." -ForegroundColor Cyan
    $qargs = @($jargs | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } })
    $proc = Start-Process -FilePath $JMeter -ArgumentList $qargs -NoNewWindow -PassThru
    # Early finish. JMeter's schedule ends with a fixed drain pause. Once the arrival window is over, no new request can start,
    # so when every request that started has finished (JMeter's own log: "Thread started" count == "Thread finished" count)
    # the rest of the pause is dead time and we stop JMeter. Nothing in flight is ever cut. The pause stays in the plan as the
    # safety net, and -NoEarlyFinish waits for it in full. (JMeter's graceful "Shutdown" does not help: it still waits out the pause.)
    $log = Join-Path $dir 'jmeter.log'
    $testStart = $null
    $stopSentAt = $null
    function Get-Count([string]$Pattern) { (Select-String -Path $log -Pattern $Pattern -SimpleMatch -ErrorAction SilentlyContinue | Measure-Object).Count }
    while (-not $proc.HasExited) {
        Start-Sleep -Seconds 2
        if ($NoEarlyFinish -or -not (Test-Path $log)) { continue }
        if (-not $testStart) {
            if (Get-Count 'Running the test!') { $testStart = Get-Date }
            continue
        }
        if ((Get-Date) -lt $testStart.AddSeconds([int]$s.duration_sec + 3)) { continue }
        $started = Get-Count 'JMeterThread: Thread started:'
        $finished = Get-Count 'JMeterThread: Thread finished:'
        if (-not $stopSentAt) {
            if ($started -gt 0 -and $started -eq $finished) {
                $udp = New-Object System.Net.Sockets.UdpClient
                $bytes = [Text.Encoding]::ASCII.GetBytes('StopTestNow')
                [void]$udp.Send($bytes, $bytes.Length, '127.0.0.1', 4445)
                $udp.Close()
                $stopSentAt = Get-Date
                Write-Host "  window over and all $started requests finished: stopping JMeter early (skipping the rest of the drain pause)" -ForegroundColor Cyan
            }
        }
        elseif (((Get-Date) - $stopSentAt).TotalSeconds -gt 30) {
            $rows = @(Get-Content -LiteralPath $jtl -ErrorAction SilentlyContinue).Count - 1   # minus the header
            if ($rows -eq $started) { & taskkill /PID $proc.Id /T /F | Out-Null; Write-Host "  JMeter did not exit by itself; stopped it (all $rows results already in the .jtl)" -ForegroundColor Yellow; break }
            $stopSentAt = Get-Date   # results not all written yet: keep waiting
        }
    }
    $proc.WaitForExit()
    $code = $proc.ExitCode
    Write-Host ("  JMeter exited with code {0} after {1:N1} min" -f $code, ((Get-Date) - $t0).TotalMinutes)
    if (-not (Test-Path $jtl)) { throw "No .jtl was written. See $(Join-Path $dir 'jmeter.log')." }

    $out = Join-Path $dir 'client_summary.json'
    & $py -I $Summary --jtl $jtl --out $out | Out-Host
    $c = Get-Content $out -Raw | ConvertFrom-Json
    $report = @{ run_id = $runId; jmeter_exit = $code; sent = $c.sent; completed_ok = $c.completed_ok; errored = $c.errored; p50_ms = $c.p50_ms }
    Invoke-RestMethod -Method Post -Uri "$ControlUrl/done" -Body ($report | ConvertTo-Json) -ContentType 'application/json' -TimeoutSec 15 | Out-Null
    Write-Host "  reported DONE to P1 (sent=$($c.sent), ok=$($c.completed_ok), errors=$($c.errored), p50=$($c.p50_ms) ms)" -ForegroundColor Green
    if ($Once) { break }
}
