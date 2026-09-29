<#
.SYNOPSIS
  Switches the SUT to another candidate model (handoff Phase K, steps 2-4).
.DESCRIPTION
  Writes OLLAMA_MODEL to .env, unloads every other model from RAM, recreates only the server
  container, then checks via /health that the server really uses the requested model.
  Follow it with prepare_run.ps1 (warm-up, clean state, READY).
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\p1\switch_model.ps1 -Model phi3:3.8b
#>
param(
    [Parameter(Mandatory = $true)][string]$Model
)
. "$PSScriptRoot\_common.ps1"

if ($Candidates -notcontains $Model) {
    throw "'$Model' is not one of the frozen Step 4 candidates: $($Candidates -join ', ')"
}
$digest = Assert-PinnedDigest $Model
Write-Ok "$Model is pulled and matches its pinned digest ($($digest.Substring(0, 12)))"

Write-Step "Setting OLLAMA_MODEL=$Model in .env"
Set-DotEnvValue -Key 'OLLAMA_MODEL' -Value $Model
# A value left in this shell would override .env when compose runs, so set it here too.
$env:OLLAMA_MODEL = $Model

foreach ($loaded in Get-LoadedModels) {
    if ($loaded.name -ne $Model) {
        Write-Step "Unloading $($loaded.name) from RAM"
        $body = @{ model = $loaded.name; keep_alive = 0 } | ConvertTo-Json
        Invoke-RestMethod -Method Post -Uri "$OllamaUrl/api/generate" -Body $body -ContentType 'application/json' | Out-Null
    }
}

Write-Step 'Recreating the server container (Ollama and MySQL keep running)'
Invoke-Compose @('up', '-d', '--no-deps', '--force-recreate', 'server') | Out-Null
$health = Wait-Health
if ($health.model -ne $Model) {
    throw "Server reports model '$($health.model)', expected '$Model'. Is OLLAMA_MODEL set elsewhere (system env var)?"
}
Write-Ok "Server now classifies with $Model (prompt $($health.prompt_version), think=$($health.think))"
Write-Host ''
Write-Host "Next: scripts\p1\prepare_run.ps1 -TestType <load|accuracy|stress> -Config <label> -Run <n> -Tester <P2..P5>"
