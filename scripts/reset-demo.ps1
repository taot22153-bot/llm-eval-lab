$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $env:LOCALAPPDATA "LLMEvalLab"
$configPath = Join-Path $runtimeRoot "my.ini"
$mysqld = "C:\Program Files\MySQL\MySQL Server 8.4\bin\mysqld.exe"
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path (Join-Path $projectRoot ".env"))) {
    throw "Missing .env. Run scripts\setup-local.ps1 first."
}
if (-not (Test-Path $configPath) -or -not (Test-Path $mysqld) -or -not (Test-Path $python)) {
    throw "Local prerequisites are incomplete. Run scripts\setup-local.ps1 first."
}

$listener = Get-NetTCPConnection -LocalPort 3307 -State Listen -ErrorAction SilentlyContinue
if (-not $listener) {
    Start-Process -FilePath $mysqld -ArgumentList "--defaults-file=$configPath" -WindowStyle Hidden
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 500
        $listener = Get-NetTCPConnection -LocalPort 3307 -State Listen -ErrorAction SilentlyContinue
        if ($listener) {
            break
        }
    }
}
if (-not $listener) {
    throw "MySQL did not start on 127.0.0.1:3307. See $runtimeRoot\mysql-error.log."
}

Push-Location $projectRoot
try {
    & $python -m alembic -c backend\alembic.ini upgrade head
    if ($LASTEXITCODE -ne 0) {
        throw "Database migration failed."
    }
    & $python -m llm_eval_lab.demo_scenario --reset
    if ($LASTEXITCODE -ne 0) {
        throw "Offline demo reset failed."
    }
} finally {
    Pop-Location
}

Write-Output "Demo reset complete. Only exact fixed-version-pair comparison evidence was cleared; unrelated data was retained."
