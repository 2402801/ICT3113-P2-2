<#
.SYNOPSIS
  Test-day preflight for the official SUT laptop (handoff section 22). Read-only.
.DESCRIPTION
  Prints PASS / WARN / FAIL for every check and exits with code 1 if anything FAILs.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\p1\preflight.ps1
#>
. "$PSScriptRoot\_common.ps1"

$results = New-Object System.Collections.Generic.List[object]
function Add-Check([string]$Name, [string]$Status, [string]$Detail) {
    $results.Add([pscustomobject]@{ Check = $Name; Status = $Status; Detail = $Detail })
}
function Test-Step([string]$Name, [scriptblock]$Body) {
    try { & $Body } catch { Add-Check $Name 'FAIL' "$_" }
}

Test-Step 'AC power / power mode' {
    $p = Get-PowerState
    if ($p.on_ac_power -and $p.power_mode -eq 'Best performance') { Add-Check 'AC power / power mode' 'PASS' 'AC, Best performance' }
    else { Add-Check 'AC power / power mode' 'WARN' "on_ac=$($p.on_ac_power) battery=$($p.battery_pct)% mode=$($p.power_mode)" }
}

Test-Step 'Native Windows Ollama stopped' {
    $procs = @(Get-Process -Name 'ollama*' -ErrorAction SilentlyContinue)
    if ($procs.Count -eq 0) { Add-Check 'Native Windows Ollama stopped' 'PASS' 'no ollama*.exe processes' }
    else { Add-Check 'Native Windows Ollama stopped' 'FAIL' "running: $(($procs | ForEach-Object { $_.Name }) -join ', ')" }
}

Test-Step 'Docker engine' {
    $v = Invoke-Native -Exe 'docker' -Arguments @('version', '--format', '{{.Server.Version}}') | Select-Object -First 1
    Add-Check 'Docker engine' 'PASS' "server $v"
}

Test-Step 'Compose services' {
    $ps = Invoke-Compose @('ps', '--format', '{{.Service}}={{.State}}/{{.Health}}')
    $state = @{}
    foreach ($line in $ps) { $kv = $line -split '=', 2; if ($kv.Count -eq 2) { $state[$kv[0]] = $kv[1] } }
    $ok = ($state['mysql'] -eq 'running/healthy') -and ($state['ollama'] -eq 'running/healthy') -and ($state['server'] -like 'running*')
    $detail = ($state.Keys | Sort-Object | ForEach-Object { "$_=$($state[$_])" }) -join '  '
    if ($ok) { Add-Check 'Compose services' 'PASS' $detail } else { Add-Check 'Compose services' 'FAIL' $detail }
}

Test-Step 'Service /health' {
    $h = Get-Health
    Add-Check 'Service /health' 'PASS' "model=$($h.model) prompt=$($h.prompt_version) think=$($h.think)"
}

Test-Step 'Candidate models pulled + pinned' {
    $inv = @(Get-ModelInventory)
    $problems = @()
    foreach ($m in $Candidates) {
        $cur = $inv | Where-Object { $_.tag -eq $m }
        $pin = Get-PinnedDigest $m
        if (-not $cur) { $problems += "$m missing" }
        elseif (-not $pin) { $problems += "$m not pinned" }
        elseif ($cur.digest -ne $pin) { $problems += "$m digest changed" }
    }
    if ($problems.Count -eq 0) { Add-Check 'Candidate models pulled + pinned' 'PASS' "$($Candidates.Count) models match tests\environment\model_pins.json" }
    else { Add-Check 'Candidate models pulled + pinned' 'FAIL' ($problems -join '; ') }
}

Test-Step 'CPU-only inference' {
    $loaded = @(Get-LoadedModels)
    if ($loaded.Count -eq 0) { Add-Check 'CPU-only inference' 'WARN' 'no model loaded yet (prepare_run.ps1 warms one up and checks)' }
    elseif (@($loaded | Where-Object { $_.size_vram -gt 0 }).Count -gt 0) { Add-Check 'CPU-only inference' 'FAIL' 'a loaded model uses VRAM' }
    else { Add-Check 'CPU-only inference' 'PASS' "loaded: $(($loaded | ForEach-Object { $_.name }) -join ', '), size_vram=0" }
}

Test-Step 'Container clock vs Windows clock' {
    # WSL2's clock can drift after the laptop sleeps; log timestamps must line up with JMeter's.
    $before = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    $inside = [double](Invoke-Compose @('exec', '-T', 'server', 'python', '-c', 'import time; print(int(time.time()*1000))') | Select-Object -Last 1)
    $after = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    $offset = $inside - ($before + $after) / 2
    $window = $after - $before
    $detail = 'offset {0:N0} ms (+/- {1:N0} ms)' -f $offset, ($window / 2)
    if ([math]::Abs($offset) -le 1000) { Add-Check 'Container clock vs Windows clock' 'PASS' $detail }
    else { Add-Check 'Container clock vs Windows clock' 'WARN' "$detail - restart Docker Desktop to resync" }
}

Test-Step 'Database state' {
    $c = Get-DbCounts
    Add-Check 'Database state' 'INFO' "tickets=$($c.tickets) request_metrics=$($c.request_metrics) (prepare_run.ps1 resets to 0)"
}

Test-Step 'Git baseline' {
    $g = Get-GitInfo
    if ($g.dirty) { Add-Check 'Git baseline' 'WARN' "$($g.branch) @ $($g.commit.Substring(0, 12)) has uncommitted changes" }
    else { Add-Check 'Git baseline' 'PASS' "$($g.branch) @ $($g.commit.Substring(0, 12)), clean" }
}

Test-Step 'Frozen golden set + prediction record' {
    $found = @()
    foreach ($f in @('datasets/golden_test_set.csv', 'datasets/labelling_protocol_v3.md', 'datasets/PredictionRecord.pdf')) {
        $c = Invoke-Native -Exe 'git' -Arguments @('-C', $RepoRoot, 'log', '--all', '-1', '--format=%h %cs', '--', $f) | Select-Object -First 1
        if ($c) { $found += "$(Split-Path $f -Leaf) $c" }
    }
    if ($found.Count -eq 3) { Add-Check 'Frozen golden set + prediction record' 'PASS' ($found -join '; ') }
    else { Add-Check 'Frozen golden set + prediction record' 'FAIL' "only found: $($found -join '; ')" }
}

Test-Step 'Firewall rule TCP 8000' {
    $rule = Get-NetFirewallRule -DisplayName 'ICT3113 SUT API (TCP 8000)' -ErrorAction SilentlyContinue
    if ($rule -and $rule.Enabled -eq 'True') { Add-Check 'Firewall rule TCP 8000' 'PASS' 'inbound allow, local subnet' }
    else { Add-Check 'Firewall rule TCP 8000' 'WARN' 'rule missing - teammates may be blocked (see runbook, needs admin)' }
}

Test-Step 'LAN address' {
    $ip = Get-LanIPv4
    $prof = Get-NetConnectionProfile | Select-Object -First 1
    $adapter = Get-NetAdapter | Where-Object { $_.Status -eq 'Up' -and $_.InterfaceDescription -notmatch 'Hyper-V|Virtual' } | Select-Object -First 1
    Add-Check 'LAN address' 'INFO' "http://${ip}:8000 via $($adapter.Name) ($($adapter.LinkSpeed)), network '$($prof.Name)' [$($prof.NetworkCategory)]"
}

$results | Format-Table -AutoSize -Wrap | Out-String -Width 220 | Write-Host
$fails = @($results | Where-Object { $_.Status -eq 'FAIL' }).Count
$warns = @($results | Where-Object { $_.Status -eq 'WARN' }).Count
if ($fails -gt 0) { Write-Host "PREFLIGHT FAILED: $fails fail(s), $warns warning(s)" -ForegroundColor Red; exit 1 }
Write-Host "PREFLIGHT OK: $warns warning(s)" -ForegroundColor Green
