<#
.SYNOPSIS
  Run on the LOAD-GENERATOR laptop (not the SUT). Records its hardware/software and the network
  path to the SUT for Slide 7, and proves the two are separate machines.
.DESCRIPTION
  Standalone: needs only Windows PowerShell 5.1. Read-only apart from the output file.
  Commit the output to tests\environment\ in the team repo.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\record_loadgen_environment.ps1 -SutHost 192.168.0.104
#>
param(
    [Parameter(Mandatory = $true)][string]$SutHost,   # the SUT laptop's LAN IPv4 (P1 prints it)
    [int]$Port = 8000,
    [int]$Samples = 20,
    [string]$OutFile = ''
)
$ErrorActionPreference = 'Stop'
if (-not $OutFile) { $OutFile = Join-Path (Get-Location) 'loadgen_environment.md' }

function Get-OrDefault([scriptblock]$Body, [string]$Fallback = 'n/a') {
    try { $v = & $Body; if ($null -eq $v -or "$v" -eq '') { return $Fallback }; return $v } catch { return "$Fallback ($_)" }
}

$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$cs = Get-CimInstance Win32_ComputerSystem
$os = Get-CimInstance Win32_OperatingSystem
$java = Get-OrDefault {
    $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    try { ((& java -version 2>&1) | ForEach-Object { "$_" } | Select-Object -First 1) } finally { $ErrorActionPreference = $prev }
}
$jmeter = Get-OrDefault {
    $cmd = Get-Command jmeter.bat, jmeter -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($cmd) { $cmd.Source } else { 'not on PATH - fill in the JMeter version used' }
}
$netCfg = Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up' } | Select-Object -First 1
$adapter = $null
if ($netCfg) { $adapter = Get-NetAdapter -InterfaceIndex $netCfg.InterfaceIndex }
$myIp = 'n/a'
if ($netCfg) { $myIp = ($netCfg.IPv4Address | Select-Object -First 1).IPAddress }
$ssid = Get-OrDefault { ((netsh wlan show interfaces) | Where-Object { $_ -match '^\s+SSID\s+:' } | Select-Object -First 1) -replace '^\s+SSID\s+:\s*', '' }

Write-Host "==> Testing TCP $SutHost`:$Port"
$tcp = Test-NetConnection -ComputerName $SutHost -Port $Port -WarningAction SilentlyContinue
$health = Get-OrDefault { Invoke-RestMethod -Uri "http://${SutHost}:$Port/health" -TimeoutSec 10 | ConvertTo-Json -Compress }

Write-Host "==> Measuring $Samples HTTP round trips to /health (application-level network latency)"
$rtt = @()
for ($i = 0; $i -lt $Samples; $i++) {
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    try { Invoke-RestMethod -Uri "http://${SutHost}:$Port/health" -TimeoutSec 10 | Out-Null; $rtt += $sw.Elapsed.TotalMilliseconds } catch { }
}
$rttText = 'no successful requests'
if ($rtt.Count -gt 0) {
    $sorted = $rtt | Sort-Object
    $rttText = '{0}/{1} ok; min {2:N1} ms, median {3:N1} ms, max {4:N1} ms' -f $rtt.Count, $Samples, $sorted[0], $sorted[[int][math]::Floor(($sorted.Count - 1) / 2)], $sorted[-1]
}

$lines = @(
    '# Load-generator machine - Test Environment Record'
    ''
    "Generated $((Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')) by ``scripts/record_loadgen_environment.ps1`` on the load-generator laptop."
    ''
    '| Item | Value |'
    '| --- | --- |'
    "| Computer name | $env:COMPUTERNAME |"
    "| Manufacturer / model | $($cs.Manufacturer) $($cs.Model) |"
    "| CPU | $($cpu.Name) - $($cpu.NumberOfCores) cores / $($cpu.NumberOfLogicalProcessors) threads |"
    "| RAM | $('{0:N1} GB' -f ($cs.TotalPhysicalMemory / 1GB)) |"
    "| OS | $($os.Caption) $($os.Version) (build $($os.BuildNumber)) |"
    "| Java | $java |"
    "| JMeter | $jmeter |"
    "| Adapter | $(if ($adapter) { "$($adapter.Name) - $($adapter.InterfaceDescription), $($adapter.LinkSpeed)" } else { 'n/a' }) |"
    "| Wi-Fi SSID | $ssid |"
    "| This machine's IPv4 | $myIp |"
    "| SUT target | http://${SutHost}:$Port |"
    "| Separate machines? | $(if ($myIp -ne $SutHost) { "yes - load generator $myIp, SUT $SutHost" } else { 'NO - same IP as the SUT' }) |"
    "| TCP connect to SUT | $($tcp.TcpTestSucceeded) |"
    "| SUT /health | $health |"
    "| HTTP round trip to /health | $rttText |"
)
[System.IO.File]::WriteAllText($OutFile, (($lines -join "`n") + "`n"), (New-Object System.Text.UTF8Encoding $false))
Write-Host "    OK  Wrote $OutFile" -ForegroundColor Green
