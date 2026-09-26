<#
.SYNOPSIS
  Closes one run and archives its server-side evidence into runs\<run-id>\ (handoff Phase L).
.DESCRIPTION
  Saves: server_access.log (every request of the run), tickets.tsv + request_metrics.tsv (the DB
  rows written during the run), ollama.log (Ollama's own per-request log for the run window) and
  ollama_ps_after.* (model still resident and CPU-only). Then restarts the service, prints a
  request-count summary taken from the archived log, and marks the run DONE in the register.
  The tester's own raw output (.jtl, accuracy CSV, ...) must be copied into the same folder.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\p1\finish_run.ps1 -RunId phi3-3.8b_load_1312tph_run1
#>
param(
    [Parameter(Mandatory = $true)][string]$RunId,
    [string]$Notes = ''
)
. "$PSScriptRoot\_common.ps1"

$runDir = Join-Path $RunsDir $RunId
$infoPath = Join-Path $runDir 'run_info.json'
if (-not (Test-Path $infoPath)) { throw "No prepared run '$RunId' (missing $infoPath)." }
if (Test-Path (Join-Path $runDir 'server_access.log')) { throw "Run '$RunId' is already finished." }
$info = Get-Content $infoPath -Raw | ConvertFrom-Json

Write-Step 'Snapshot of Ollama after the run'
$loaded = @(Get-LoadedModels)
Write-Utf8File -Path (Join-Path $runDir 'ollama_ps_after.json') -Content (ConvertTo-Json @($loaded) -Depth 6)
Write-Utf8File -Path (Join-Path $runDir 'ollama_ps_after.txt') -Content ((Invoke-Compose @('exec', '-T', 'ollama', 'ollama', 'ps')) -join "`n")
$gpu = @($loaded | Where-Object { $_.size_vram -gt 0 })
if ($gpu.Count -gt 0) { Write-Warn "GPU memory in use by $($gpu.name -join ', ') - this run is NOT valid evidence." }
else { Write-Ok 'still CPU only' }

Write-Step 'Archiving the service log'
Invoke-Compose @('stop', 'server') | Out-Null
$logDest = Join-Path $runDir 'server_access.log'
if (Test-Path $AccessLog) { Move-Item -Path $AccessLog -Destination $logDest }
else { Write-Warn 'No access.log found - the service handled no requests?'; Write-Utf8File -Path $logDest -Content '' }
Write-Ok "runs\$RunId\server_access.log"

Write-Step 'Exporting the database rows written during the run'
Export-Table -Table 'tickets' -Destination (Join-Path $runDir 'tickets.tsv')
Export-Table -Table 'request_metrics' -Destination (Join-Path $runDir 'request_metrics.tsv')
$counts = Get-DbCounts
Write-Ok "tickets.tsv ($($counts.tickets) rows), request_metrics.tsv ($($counts.request_metrics) rows)"

Write-Step "Saving Ollama's own log for the run window"
$ollamaLog = Invoke-Compose @('logs', '--no-color', '--since', $info.ready_at_utc, 'ollama')
Write-Utf8File -Path (Join-Path $runDir 'ollama.log') -Content (($ollamaLog -join "`n") + "`n")
Write-Ok "runs\$RunId\ollama.log"

Write-Step 'Restarting the service for the next run'
Invoke-Compose @('start', 'server') | Out-Null
Wait-Health | Out-Null
Write-Ok 'service healthy'

Write-Step 'Request counts in the archived log (method path status -> count)'
$summary = Get-Content $logDest | ForEach-Object {
    if ($_ -match '^\S+ (\S+) (\S+) (\d{3}) ') { "$($Matches[1]) $($Matches[2]) $($Matches[3])" }
} | Group-Object | Sort-Object Name
$summary | ForEach-Object { Write-Host ('    {0,-28} {1,7}' -f $_.Name, $_.Count) }
$posted = @($summary | Where-Object { $_.Name -eq 'POST /tickets 200' })
$posted200 = 0
if ($posted.Count -gt 0) { $posted200 = $posted[0].Count }
if ($posted200 -ne $counts.tickets) {
    Write-Warn "Log shows $posted200 successful POST /tickets but the DB holds $($counts.tickets) tickets - investigate."
}
else { Write-Ok 'log and database agree on the number of stored tickets' }

Update-RegisterRow -RunId $RunId -Changes @{
    status = 'DONE'; finished_at_utc = (Get-UtcStamp); server_log = "runs/$RunId/server_access.log"; notes = (@($info.notes, $Notes) | Where-Object { $_ }) -join ' | '
}

Write-Host ''
Write-Host "DONE  $RunId" -ForegroundColor Green
Write-Host "  Ask $($info.tester) to copy their raw results (e.g. results.jtl / accuracy CSV) into runs\$RunId\"
Write-Host '  Then commit the runs\ folder so every reported number stays traceable.'
