param(
    [switch]$SmokeTest
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $env:LOCALAPPDATA "LLMEvalLab"
$configPath = Join-Path $runtimeRoot "my.ini"
$mysqld = "C:\Program Files\MySQL\MySQL Server 8.4\bin\mysqld.exe"
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$nodeDir = "C:\Program Files\nodejs"
$npm = Join-Path $nodeDir "npm.cmd"
$env:Path = "$nodeDir;$env:Path"
$backend = $null
$frontend = $null

function Stop-ProcessTree {
    param([System.Diagnostics.Process]$Process)

    if ($Process -and -not $Process.HasExited) {
        & taskkill.exe /PID $Process.Id /T /F 2>$null | Out-Null
    }
}

function Wait-HttpEndpoint {
    param([string]$Url)

    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 1
            if ($response.StatusCode -eq 200) {
                return
            }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    throw "Endpoint did not become ready: $Url"
}

if (-not (Test-Path (Join-Path $projectRoot ".env"))) {
    throw "Missing .env. Run scripts\setup-local.ps1 first."
}
if (-not (Test-Path $configPath) -or -not (Test-Path $python) -or -not (Test-Path $npm)) {
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
    throw "MySQL did not start on 127.0.0.1:3307."
}

Push-Location $projectRoot
try {
    & $python -m alembic -c backend\alembic.ini upgrade head
    if ($LASTEXITCODE -ne 0) {
        throw "Database migration failed."
    }
    & $python -m llm_eval_lab.sample_suite
    if ($LASTEXITCODE -ne 0) {
        throw "Sample Evaluation Suite seed failed."
    }

    $backend = Start-Process -FilePath $python -ArgumentList @(
        "-m", "uvicorn", "llm_eval_lab.main:app",
        "--app-dir", "backend/src", "--host", "127.0.0.1", "--port", "8000"
    ) -WorkingDirectory $projectRoot -NoNewWindow -PassThru
    $frontend = Start-Process -FilePath $npm -ArgumentList @(
        "--prefix", "frontend", "run", "dev"
    ) -WorkingDirectory $projectRoot -NoNewWindow -PassThru

    Start-Sleep -Seconds 2
    if ($backend.HasExited -or $frontend.HasExited) {
        throw "A development server exited during startup."
    }

    Write-Output "LLM Eval Lab is running at http://127.0.0.1:5173"
    Write-Output "FastAPI documentation is at http://127.0.0.1:8000/docs"
    Write-Output "Press Ctrl+C to stop the Web console and API."

    if ($SmokeTest) {
        Wait-HttpEndpoint -Url "http://127.0.0.1:8000/openapi.json"
        Wait-HttpEndpoint -Url "http://127.0.0.1:5173"
        Write-Output "Startup smoke test passed."
        return
    }

    while (-not $backend.HasExited -and -not $frontend.HasExited) {
        Start-Sleep -Seconds 1
    }
} finally {
    Stop-ProcessTree -Process $backend
    Stop-ProcessTree -Process $frontend
    Pop-Location
}
