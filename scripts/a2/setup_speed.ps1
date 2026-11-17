<#
.SYNOPSIS
  P1, once, before the speed runs: pick the 3 fixed warm-up tickets, measure S on the top model, derive rate / run length / timeout / pause.
.DESCRIPTION
  Needs datasets\a2\speed\*.jsonl from P2 (python scripts\a2\build_speed_workload.py), committed.
  1. Cascade S1 is started; each warm-up candidate is sent until 3 are found that ESCALATE under both S1 and S2
     (phi3 answers Bank account or service / Credit reporting). Those 3 become warmup_tickets.jsonl, used for every run.
  2. gemma4 alone is started, warmed up with those 3, then the 3 S-probe tickets are sent one at a time.
     S = the middle time (client-side seconds, as JMeter would see it).
  3. Writes datasets\a2\speed\speed_params.json (+ evidence in datasets\a2\speed\s_measurement\).
  Run on the official SUT laptop with Docker up. Commit datasets\a2\speed\ afterwards.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\a2\setup_speed.ps1
#>
param(
    [int]$ClientPeakPerHour = 3936,   # A1 workload model, TR-2 peak (docs\LOAD_TEST_PLAYBOOK.md)
    # 0 = the brief's rule (S minutes, minimum 5). A value such as 5 SHORTENS every run: a deliberate deviation from the brief,
    # recorded in speed_params.json; it must be declared on slides 3 and 8. The rate is unchanged, so fewer tickets are sent.
    [double]$DurationMinutes = 0
)
. "$PSScriptRoot\_a2common.ps1"

foreach ($f in 'warmup_candidates.jsonl', 's_probe_tickets.jsonl', 'workload_manifest.json') {
    if (-not (Test-Path (Join-Path $SpeedDir $f))) { throw "Missing $f in $SpeedDir. P2: run python scripts\a2\build_speed_workload.py and commit." }
}
$evidence = Join-Path $SpeedDir 's_measurement'
New-Item -ItemType Directory -Force -Path $evidence | Out-Null

# ---- 1. warm-up tickets that escalate under both settings
Set-A2Config 'cascadeS1'
Write-Step 'Choosing the fixed warm-up tickets (must escalate under S1 and S2)'
$chosen = New-Object System.Collections.Generic.List[string]
$choice = New-Object System.Collections.Generic.List[object]
$candidates = Read-Jsonl (Join-Path $SpeedDir 'warmup_candidates.jsonl')
$i = 0
foreach ($text in $candidates) {
    $i++
    if ($chosen.Count -ge 3) { break }
    $r = Send-Ticket -Narrative $text -RunId 'a2-warmup-pick'
    $f = Get-LogFields $r.req_id
    $ok = ($f['escalated'] -eq '1') -and (@('Bank account or service', 'Credit reporting') -contains $f['small_answer'])
    Write-Host ("    candidate {0}: phi3='{1}' escalated={2} final='{3}' {4:N1}s {5}" -f $i, $f['small_answer'], $f['escalated'], $r.body.category, $r.seconds, $(if ($ok) { '<- chosen' } else { '' }))
    if ($ok) { $chosen.Add($text); $choice.Add([ordered]@{ candidate_index = $i; small_answer = $f['small_answer']; final_category = $r.body.category }) }
}
if ($chosen.Count -lt 3) { throw "Only $($chosen.Count) escalating warm-up candidates found; add more candidates." }
$lines = $chosen | ForEach-Object { (@{ narrative = $_ } | ConvertTo-Json -Compress) }
Write-Utf8File -Path $WarmupPath -Content (($lines -join "`n") + "`n")
Write-Ok "warmup_tickets.jsonl written (3 tickets)"

# ---- 2. S on the top model
Set-A2Config 'gemmaAlone'
Write-Step 'Warm-up on gemma4 alone (not timed)'
foreach ($text in (Read-Jsonl $WarmupPath)) { $r = Send-Ticket -Narrative $text -RunId 'a2-s-warmup'; Write-Ok ("warm-up {0:N1}s" -f $r.seconds) }
Write-Step 'Measuring S: three different typical tickets, one at a time'
$times = New-Object System.Collections.Generic.List[double]
foreach ($text in (Read-Jsonl (Join-Path $SpeedDir 's_probe_tickets.jsonl'))) {
    $r = Send-Ticket -Narrative $text -RunId 'a2-s-probe'
    $times.Add([math]::Round($r.seconds, 2))
    Write-Ok ("probe {0}: {1:N2}s (category {2})" -f $times.Count, $r.seconds, $r.body.category)
}
$sorted = @($times | Sort-Object)
$S = $sorted[1]   # the middle of three
Write-Utf8File -Path (Join-Path $evidence 'ollama_ps.txt') -Content ((Invoke-Compose @('exec', '-T', 'ollama', 'ollama', 'ps')) -join "`n")
Copy-Item -Path $AccessLog -Destination (Join-Path $evidence 'server_access.log') -Force

# ---- 3. parameters
$manifest = Get-Content (Join-Path $SpeedDir 'workload_manifest.json') -Raw | ConvertFrom-Json
$rate = [int][math]::Max(1, [math]::Round(3600 / (2 * $S)))
$duration = [int][math]::Max(300, [math]::Round($S * 60))
$deviation = 'none: duration = max(S min, 5 min) as in the brief'
if ($DurationMinutes -gt 0) {
    $duration = [int][math]::Round($DurationMinutes * 60)
    $deviation = "DEVIATION from the brief: run length forced to $DurationMinutes min (the brief says S min, minimum 5). Rate and timeout unchanged."
}
$timeout = [int][math]::Max(300, [math]::Ceiling(10 * $S))
$pause = $timeout + 90
$expected = [math]::Round($rate * $duration / 3600, 1)
$params = [ordered]@{
    s_seconds              = $S
    s_timings_seconds      = @($times)
    s_probe_source_rows    = @($manifest.probe_rows)
    model_for_s            = 'gemma4:e4b (cascade off)'
    rate_per_hour          = $rate
    interarrival_seconds   = [math]::Round(3600 / $rate, 1)
    duration_sec           = $duration
    response_timeout_sec   = $timeout
    pause_sec              = $pause
    expected_tickets       = $expected
    a1_client_peak_per_hour = $ClientPeakPerHour
    rate_vs_client_peak    = $(if ($rate -ge $ClientPeakPerHour) { 'at or above the client peak: also shows the system handles the client load' } else { 'BELOW the client peak: compares configurations only; say so on the limitations slide' })
    run_length_deviation   = $deviation
    recorded_at_utc        = (Get-UtcStamp)
    rule                   = 'rate = 1 ticket per 2S s (rounded to a whole number per hour); duration = max(S min, 5 min); timeout = max(10S, 300 s); pause = timeout + 90 s'
}
Write-Utf8File -Path $ParamsPath -Content ((ConvertTo-Json $params -Depth 4) + "`n")

Write-Host ''
Write-Host "S = $S s  (timings: $($times -join ', '))" -ForegroundColor Green
Write-Host "rate = $rate / hour (one every $([math]::Round(3600 / $rate, 1)) s), run length $duration s, timeout $timeout s, pause $pause s, about $expected tickets per run"
if ($DurationMinutes -gt 0) { Write-Warn "$deviation Only about $expected tickets per run (about $([math]::Round(3 * $expected)) pooled over 3 runs): p50 per run and the pooled p95 will be very weak." }
if ($expected -gt 45) { Write-Warn 'More than 45 expected tickets: the workload file (45 rows) may run out. Rebuild with a larger N_WORKLOAD.' }
Write-Host "Written: $ParamsPath"
Write-Host 'Next: commit datasets\a2\speed\, then scripts\a2\p1_run_all.ps1 (P1) and scripts\a2\p2_run_loop.ps1 (P2).'
