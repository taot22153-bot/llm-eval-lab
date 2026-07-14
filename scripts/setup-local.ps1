$ErrorActionPreference = "Stop"

function Get-RandomPassword {
    param([int]$Length)

    $alphabet = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return -join (1..$Length | ForEach-Object {
        $alphabet[(Get-Random -Maximum $alphabet.Length)]
    })
}

function Read-KeyValueFile {
    param([string]$Path)

    $values = @{}
    foreach ($line in Get-Content -Path $Path) {
        if ($line -match "^([^#=]+)=(.*)$") {
            $values[$matches[1]] = $matches[2]
        }
    }
    return $values
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $env:LOCALAPPDATA "LLMEvalLab"
$dataDir = Join-Path $runtimeRoot "mysql-data"
$configPath = Join-Path $runtimeRoot "my.ini"
$credentialsPath = Join-Path $runtimeRoot "credentials.env"
$mysqlBin = "C:\Program Files\MySQL\MySQL Server 8.4\bin"
$mysqld = Join-Path $mysqlBin "mysqld.exe"
$mysql = Join-Path $mysqlBin "mysql.exe"
$pythonLauncher = (Get-Command py -ErrorAction SilentlyContinue).Source
$nodeDir = "C:\Program Files\nodejs"
$node = Join-Path $nodeDir "node.exe"
$npm = Join-Path $nodeDir "npm.cmd"
$env:Path = "$nodeDir;$env:Path"

if (-not $pythonLauncher) {
    throw "Python Launcher is missing. Install Python 3.12 with: winget install --id Python.Python.3.12 --exact"
}
& $pythonLauncher -3.12 --version | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Python 3.12 is missing. Install it with: winget install --id Python.Python.3.12 --exact"
}
if (-not (Test-Path $node) -or -not (Test-Path $npm)) {
    throw "Node.js LTS is missing. Install it with: winget install --id OpenJS.NodeJS.LTS --exact"
}
if (-not (Test-Path $mysqld) -or -not (Test-Path $mysql)) {
    throw "MySQL 8.4 is missing. Install it with: winget install --id Oracle.MySQL --exact"
}

New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
$configDataDir = $dataDir.Replace("\", "/")
$configRuntimeRoot = $runtimeRoot.Replace("\", "/")
$config = @"
[mysqld]
basedir=C:/Program Files/MySQL/MySQL Server 8.4
datadir=$configDataDir
port=3307
bind-address=127.0.0.1
mysqlx=0
character-set-server=utf8mb4
collation-server=utf8mb4_0900_ai_ci
log-error=$configRuntimeRoot/mysql-error.log

[client]
port=3307
host=127.0.0.1
default-character-set=utf8mb4
"@
[System.IO.File]::WriteAllText(
    $configPath,
    $config,
    [System.Text.UTF8Encoding]::new($false)
)

$isNewInstance = -not (Test-Path (Join-Path $dataDir "mysql"))
if ($isNewInstance) {
    & $mysqld "--defaults-file=$configPath" --initialize-insecure --console
    if ($LASTEXITCODE -ne 0) {
        throw "MySQL initialization failed. See $runtimeRoot\mysql-error.log."
    }
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

if ($isNewInstance) {
    $appPassword = Get-RandomPassword -Length 32
    $rootPassword = Get-RandomPassword -Length 40
    $sql = @"
CREATE DATABASE IF NOT EXISTS llm_eval_lab CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE DATABASE IF NOT EXISTS llm_eval_lab_test CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE USER 'llm_eval_lab'@'127.0.0.1' IDENTIFIED BY '$appPassword';
GRANT ALL PRIVILEGES ON llm_eval_lab.* TO 'llm_eval_lab'@'127.0.0.1';
GRANT ALL PRIVILEGES ON llm_eval_lab_test.* TO 'llm_eval_lab'@'127.0.0.1';
ALTER USER 'root'@'localhost' IDENTIFIED BY '$rootPassword';
FLUSH PRIVILEGES;
"@
    $sql | & $mysql --protocol=tcp --host=127.0.0.1 --port=3307 --user=root
    if ($LASTEXITCODE -ne 0) {
        throw "MySQL database and user setup failed."
    }
    $credentialContent = "MYSQL_ROOT_PASSWORD=$rootPassword`nMYSQL_APP_PASSWORD=$appPassword`n"
    [System.IO.File]::WriteAllText(
        $credentialsPath,
        $credentialContent,
        [System.Text.UTF8Encoding]::new($false)
    )
} elseif (-not (Test-Path $credentialsPath)) {
    throw "MySQL data exists but $credentialsPath is missing. Restore it or reset the local runtime directory."
}

$credentials = Read-KeyValueFile -Path $credentialsPath
$appPassword = $credentials["MYSQL_APP_PASSWORD"]
if (-not $appPassword) {
    throw "MYSQL_APP_PASSWORD is missing from $credentialsPath."
}

$envContent = @"
DATABASE_URL=mysql+pymysql://llm_eval_lab:$appPassword@127.0.0.1:3307/llm_eval_lab
TEST_DATABASE_URL=mysql+pymysql://llm_eval_lab:$appPassword@127.0.0.1:3307/llm_eval_lab_test
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
"@
[System.IO.File]::WriteAllText(
    (Join-Path $projectRoot ".env"),
    $envContent,
    [System.Text.UTF8Encoding]::new($false)
)

$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    & $pythonLauncher -3.12 -m venv (Join-Path $projectRoot ".venv")
}
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -e "$projectRoot\backend[dev]"

Push-Location $projectRoot
try {
    & $npm --prefix frontend ci
    & $venvPython -m alembic -c backend\alembic.ini upgrade head
    if ($LASTEXITCODE -ne 0) {
        throw "Database migration failed."
    }
    & $venvPython -m llm_eval_lab.sample_suite
    if ($LASTEXITCODE -ne 0) {
        throw "Sample Evaluation Suite seed failed."
    }
} finally {
    Pop-Location
}

Write-Output "Local setup complete. Run scripts\start-dev.ps1 from the repository root."
