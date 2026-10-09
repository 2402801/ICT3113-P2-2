<#
.SYNOPSIS
  Records the official SUT laptop's hardware / software / network state (Slide 7 evidence).
.DESCRIPTION
  Writes tests\environment\p1_sut_environment.md. Re-run it on test day and commit the result;
  git history keeps every version. Read-only apart from that file.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\p1\record_environment.ps1
#>
param([string]$OutFile = '')
. "$PSScriptRoot\_common.ps1"
if (-not $OutFile) { $OutFile = Join-Path $EnvDocDir 'p1_sut_environment.md' }
$env:WSL_UTF8 = '1'   # wsl.exe prints UTF-16 otherwise

function Get-OrDefault([scriptblock]$Body, [string]$Fallback = 'n/a') {
    try { $v = & $Body; if ($null -eq $v -or "$v" -eq '') { return $Fallback }; return $v } catch { return "$Fallback ($_)" }
}
function Get-ListOrEmpty([scriptblock]$Body) {
    try { return @(& $Body | Where-Object { $_ }) } catch { return @() }
}

$lines = New-Object System.Collections.Generic.List[string]
function Add([string]$Text = '') { $lines.Add($Text) }
function Add-Row([string]$Key, $Value) { $lines.Add("| $Key | $(("$Value") -replace '\|', '/' -replace "`r?`n", ' ') |") }

Write-Step 'Collecting SUT environment'
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$cs = Get-CimInstance Win32_ComputerSystem
$os = Get-CimInstance Win32_OperatingSystem
$gpus = (Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name }) -join '; '
$power = Get-PowerState
$git = Get-GitInfo
$health = $null
try { $health = Get-Health } catch { }
$ollamaVersion = Get-OrDefault { Get-OllamaVersion }
$dockerVersion = Get-OrDefault { (Invoke-Native -Exe 'docker' -Arguments @('version', '--format', '{{.Server.Platform.Name}} / engine {{.Server.Version}}')) -join ' ' }
$composeVersion = Get-OrDefault { (Invoke-Native -Exe 'docker' -Arguments @('compose', 'version', '--short')) -join ' ' }
$dockerVm = Get-OrDefault { (Invoke-Native -Exe 'docker' -Arguments @('info', '--format', '{{.NCPU}} vCPU, {{.MemTotal}} bytes RAM, kernel {{.KernelVersion}}')) -join ' ' }
$wsl = Get-OrDefault { (Invoke-Native -Exe 'wsl.exe' -Arguments @('--version') | Where-Object { $_ -match 'WSL version|Kernel version' }) -join '; ' }
# @() at each call site: PowerShell unrolls a one-item array returned from a function.
$ollamaLogs = @(Get-ListOrEmpty { Invoke-Compose @('logs', '--no-color', 'ollama') })
$serverConfig = $ollamaLogs | Where-Object { $_ -match 'msg="server config"' } | Select-Object -Last 1
$computeLine = $ollamaLogs | Where-Object { $_ -match 'msg="inference compute"' } | Select-Object -Last 1
function Get-OllamaSetting([string]$Name) {
    if ($serverConfig -match "$Name`:([^ \]]*)") { return $Matches[1] }
    return 'n/a'
}

$images = foreach ($svc in @('mysql', 'ollama', 'server')) {
    $id = Get-OrDefault { (Invoke-Compose @('images', '-q', $svc) | Select-Object -First 1) }
    # No embedded double quotes in the format: PowerShell 5.1 strips them when calling native exes.
    $ref = Get-OrDefault { (Invoke-Native -Exe 'docker' -Arguments @('image', 'inspect', $id, '--format', '{{json .RepoTags}} {{json .RepoDigests}}')) -join ' ' }
    [pscustomobject]@{ service = $svc; image = $ref; id = $id }
}

$netCfg = Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up' } | Select-Object -First 1
$adapter = $null
$netProfile = $null
if ($netCfg) {
    $adapter = Get-NetAdapter -InterfaceIndex $netCfg.InterfaceIndex
    $netProfile = Get-NetConnectionProfile -InterfaceIndex $netCfg.InterfaceIndex -ErrorAction SilentlyContinue
}
$ssid = Get-OrDefault { ((netsh wlan show interfaces) | Where-Object { $_ -match '^\s+SSID\s+:' } | Select-Object -First 1) -replace '^\s+SSID\s+:\s*', '' }
$fwRule = Get-NetFirewallRule -DisplayName 'ICT3113 SUT API (TCP 8000)' -ErrorAction SilentlyContinue

Add '# P1 Official SUT - Test Environment Record'
Add ''
Add "Generated $(Get-UtcStamp) by ``scripts/p1/record_environment.ps1`` on the official SUT laptop. Values are read from the machine, Docker and Ollama APIs; nothing is typed in by hand."
Add ''
Add '## SUT machine (runs the triage service, MySQL and Ollama)'
Add ''
Add '| Item | Value |'
Add '| --- | --- |'
Add-Row 'Manufacturer / model' "$($cs.Manufacturer) $($cs.Model)"
Add-Row 'CPU' "$($cpu.Name) - $($cpu.NumberOfCores) cores / $($cpu.NumberOfLogicalProcessors) threads, base $($cpu.MaxClockSpeed) MHz"
Add-Row 'RAM (host)' ('{0:N1} GB' -f ($cs.TotalPhysicalMemory / 1GB))
Add-Row 'GPU(s) present' "$gpus - NOT used: no GPU is passed into the Ollama container"
Add-Row 'OS' "$($os.Caption) $($os.Version) (build $($os.BuildNumber))"
Add-Row 'Power at record time' "AC=$($power.on_ac_power), battery $($power.battery_pct)%, Windows power mode '$($power.power_mode)'"
Add-Row 'Power scheme' $power.scheme
Add-Row 'Docker' $dockerVersion
Add-Row 'Docker Compose' $composeVersion
Add-Row 'Docker VM (WSL2) resources' $dockerVm
Add-Row 'WSL' $wsl
Add ''
Add '## Service stack (docker compose, project `ict3113-p2-2`)'
Add ''
Add '| Service | Image (tag + digest) | Image ID |'
Add '| --- | --- | --- |'
foreach ($i in $images) { $lines.Add("| $($i.service) | $($i.image) | $($i.id) |") }
Add ''
Add '| Setting | Value |'
Add '| --- | --- |'
Add-Row 'Ollama version' $ollamaVersion
$computeText = 'n/a'
if ($computeLine) { $computeText = $computeLine -replace '^.*msg=', 'msg=' }
Add-Row 'Inference compute (Ollama startup log)' $computeText
Add-Row 'OLLAMA_NUM_PARALLEL' (Get-OllamaSetting 'OLLAMA_NUM_PARALLEL')
Add-Row 'OLLAMA_MAX_LOADED_MODELS' (Get-OllamaSetting 'OLLAMA_MAX_LOADED_MODELS')
Add-Row 'OLLAMA_MAX_QUEUE' (Get-OllamaSetting 'OLLAMA_MAX_QUEUE')
Add-Row 'OLLAMA_KEEP_ALIVE' (Get-OllamaSetting 'OLLAMA_KEEP_ALIVE')
Add-Row 'OLLAMA_CONTEXT_LENGTH (0 = default, 4096 on CPU)' (Get-OllamaSetting 'OLLAMA_CONTEXT_LENGTH')
Add-Row 'OLLAMA_FLASH_ATTENTION' (Get-OllamaSetting 'OLLAMA_FLASH_ATTENTION')
$serviceText = 'service not reachable'
if ($health) { $serviceText = "model=$($health.model), prompt=$($health.prompt_version), think=$($health.think)" }
Add-Row 'Service model / prompt / think' $serviceText
Add-Row 'Classifier call' 'POST /api/generate, stream=false, temperature=0, seed=42, JSON-schema format (7-category enum), timeout 600 s'
Add ''
Add '## Candidate models (Docker Ollama store)'
Add ''
Add '| Tag | Full digest | Short ID | Step 4 ID | Size | Params | Quant |'
Add '| --- | --- | --- | --- | --- | --- | --- |'
$inventory = @(Get-ListOrEmpty { Get-ModelInventory })
foreach ($m in $Candidates) {
    $x = $inventory | Where-Object { $_.tag -eq $m }
    if ($x) {
        $match = "$($x.step4_short_id) (DIFFERENT)"
        if ($x.short_id -eq $x.step4_short_id) { $match = "$($x.step4_short_id) (match)" }
        $lines.Add(('| {0} | {1} | {2} | {3} | {4:N2} GB | {5} | {6} |' -f $x.tag, $x.digest, $x.short_id, $match, ($x.size_bytes / 1GB), $x.parameter_size, $x.quantization))
    }
    else { $lines.Add("| $m | not pulled | | $($Step4ShortIds[$m]) | | | |") }
}
Add ''
Add '## CPU-only evidence'
Add ''
if ($computeLine) { Add "- Ollama found no GPU at startup: ``$computeText``" }
$loaded = @(Get-ListOrEmpty { Get-LoadedModels })
if ($loaded.Count -gt 0) {
    foreach ($l in $loaded) { Add "- ``/api/ps``: $($l.name) resident, size=$($l.size) bytes, **size_vram=$($l.size_vram)**" }
    Add ''
    Add '```'
    foreach ($row in @(Get-ListOrEmpty { Invoke-Compose @('exec', '-T', 'ollama', 'ollama', 'ps') })) { Add $row }
    Add '```'
}
else { Add '- No model loaded at record time. `prepare_run.ps1` checks size_vram = 0 before every run and saves `ollama_ps_before.*` in the run folder.' }
Add ''
Add '## Network'
Add ''
Add '| Item | Value |'
Add '| --- | --- |'
$adapterText = 'n/a'
if ($adapter) { $adapterText = "$($adapter.Name) - $($adapter.InterfaceDescription), $($adapter.LinkSpeed)" }
Add-Row 'Adapter' $adapterText
Add-Row 'Wi-Fi SSID' $ssid
$ipText = 'n/a'
if ($netCfg) { $ipText = "$(($netCfg.IPv4Address | Select-Object -First 1).IPAddress) / $($netCfg.IPv4DefaultGateway.NextHop)" }
Add-Row 'IPv4 / gateway' $ipText
$profileText = 'n/a'
if ($netProfile) { $profileText = "$($netProfile.Name) [$($netProfile.NetworkCategory)]" }
Add-Row 'Windows network category' $profileText
Add-Row 'Service URL for testers' "http://$(Get-LanIPv4):8000"
$fwText = 'MISSING (see docs/LOAD_TEST_PLAYBOOK.md section 3.1)'
if ($fwRule) { $fwText = "present, enabled=$($fwRule.Enabled), profile=$($fwRule.Profile)" }
Add-Row 'Firewall rule for TCP 8000' $fwText
Add-Row 'MySQL 3306 / Ollama 11434' 'bound to 127.0.0.1 only - not reachable from the LAN'
Add ''
Add '## Code baseline'
Add ''
Add '| Item | Value |'
Add '| --- | --- |'
Add-Row 'Branch @ commit' "$($git.branch) @ $($git.commit)"
$dirtyText = 'none'
if ($git.dirty) { $dirtyText = "YES - $(@($git.dirty_files).Count) file(s)" }
Add-Row 'Uncommitted changes (excl. runs/, tests/environment/)' $dirtyText
foreach ($f in @('datasets/golden_test_set.csv', 'datasets/labelling_protocol_v3.md', 'datasets/PredictionRecord.pdf')) {
    Add-Row "Frozen: $f" (Get-OrDefault { (Invoke-Native -Exe 'git' -Arguments @('-C', $RepoRoot, 'log', '--all', '-1', '--format=%h %ci %an', '--', $f)) -join ' ' })
}
Add ''
Add '## Known limitations (for Slide 7)'
Add ''
Add '- Consumer gaming laptop, not a server: hybrid P/E-core CPU whose boost clocks depend on temperature and power mode, so long runs can throttle.'
Add '- Inference runs inside Docker Desktop''s WSL2 VM, which sees only part of the host RAM (see the Docker VM row); Windows and WSL add some overhead.'
Add '- Network is Wi-Fi unless noted otherwise: latency jitter between the load generator and the SUT is part of every measured response time.'
Add '- Docker Desktop port forwarding hides the tester''s real IP (the service log shows the Docker gateway), so runs are told apart by time window and the optional X-Run-Id header.'
Add '- Background Windows activity (updates, antivirus scans) cannot be fully excluded; heavy apps are closed before official runs.'

New-Item -ItemType Directory -Force -Path (Split-Path $OutFile) | Out-Null
Write-Utf8File -Path $OutFile -Content (($lines -join "`n") + "`n")
Write-Ok "Wrote $OutFile"
