<#
.SYNOPSIS
  Records the exact tag + FULL digest of every candidate model in docs\environment\model_pins.json.
.DESCRIPTION
  The pins file is what every later run is checked against: if a model's digest ever changes
  (for example after an accidental re-pull), prepare_run.ps1 refuses to start.
  Also compares each digest with the short model ID written in the frozen Step 4 document.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\p1\pin_models.ps1 -Pull
#>
param(
    [switch]$Pull,   # pull any candidate that is not in the Docker Ollama store yet
    [switch]$Force   # overwrite an existing pins file (only if the team agrees to re-pin)
)
. "$PSScriptRoot\_common.ps1"

if ($Pull) {
    $present = @(Get-ModelInventory | ForEach-Object { $_.tag })
    foreach ($model in $Candidates) {
        if ($present -contains $model) { Write-Ok "$model already pulled"; continue }
        Write-Step "Pulling $model into Docker Ollama"
        & docker compose -f $ComposeFile exec -T ollama ollama pull $model
        if ($LASTEXITCODE -ne 0) { throw "ollama pull $model failed" }
    }
}

if ((Test-Path $PinsPath) -and -not $Force) {
    throw "$PinsPath already exists. Pins are frozen once official runs start; use -Force only on purpose."
}

$inventory = @(Get-ModelInventory)
$missing = @($Candidates | Where-Object { ($inventory | ForEach-Object { $_.tag }) -notcontains $_ })
if ($missing.Count -gt 0) { throw "Not pulled yet: $($missing -join ', '). Re-run with -Pull." }

$recordedAt = Get-UtcStamp
$ollamaVersion = Get-OllamaVersion
$pins = foreach ($model in $Candidates) {
    $m = $inventory | Where-Object { $_.tag -eq $model }
    [ordered]@{
        tag              = $m.tag
        digest           = $m.digest
        short_id         = $m.short_id
        step4_short_id   = $m.step4_short_id
        matches_step4_id = ($m.short_id -eq $m.step4_short_id)
        size_bytes       = $m.size_bytes
        parameter_size   = $m.parameter_size
        quantization     = $m.quantization
        family           = $m.family
        ollama_version   = $ollamaVersion
        recorded_at_utc  = $recordedAt
    }
}

New-Item -ItemType Directory -Force -Path $EnvDocDir | Out-Null
Write-Utf8File -Path $PinsPath -Content (ConvertTo-Json @($pins) -Depth 4)

Write-Step "Pinned models -> $PinsPath"
foreach ($p in $pins) {
    $line = '{0,-12} {1}  size={2:N2} GB  params={3}  quant={4}' -f $p.tag, $p.digest, ($p.size_bytes / 1GB), $p.parameter_size, $p.quantization
    if ($p.matches_step4_id) { Write-Ok "$line  (matches Step 4 ID)" }
    else { Write-Warn "$line  (Step 4 recorded $($p.step4_short_id) - tell the team; report the digest actually tested)" }
}
