$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    if (-not (Test-Path '.venv\Scripts\python.exe') -or -not (Test-Path 'dist\index.html')) {
        throw 'Run .\scripts\setup.ps1 before starting the app.'
    }
    $env:PYTHONUTF8 = '1'
    $env:ANONYMIZED_TELEMETRY = 'False'
    Write-Host 'Zhiyu is starting at http://127.0.0.1:8765. Press Ctrl+C to stop.'
    & .venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --app-dir backend --host 127.0.0.1 --port 8765 --no-access-log
} finally { Pop-Location }
