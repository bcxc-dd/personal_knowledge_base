$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    if (-not (Test-Path '.venv\Scripts\python.exe')) {
        python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Python virtual environment creation failed.' }
    }
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        uv pip install --python .venv\Scripts\python.exe -r backend\requirements.txt
    } else {
        & .venv\Scripts\python.exe -m pip install -r backend\requirements.txt
    }
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
    npm.cmd ci
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
    npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    Write-Host 'Setup complete. Run .\scripts\start.ps1'
} finally { Pop-Location }
