param(
    [switch]$SmokeTest,
    [switch]$KeepEvidence
)

$ErrorActionPreference = "Stop"
$resetScript = Join-Path $PSScriptRoot "reset-demo.ps1"
$startScript = Join-Path $PSScriptRoot "start-dev.ps1"

if (-not $KeepEvidence) {
    & $resetScript
    if ($LASTEXITCODE -ne 0) {
        throw "Demo reset failed before startup."
    }
} else {
    Write-Output "Keeping existing demo evidence. Startup will not reset the database."
}

$env:SEMANTIC_JUDGE_PROVIDER = "demo-fixture"
$env:SEMANTIC_JUDGE_MODEL = "northstar-semantic-fixture-v1"
Write-Output "Starting deterministic offline demo mode. This fixture is not an Ollama model run."

if ($SmokeTest) {
    & $startScript -SmokeTest
} else {
    & $startScript
}
