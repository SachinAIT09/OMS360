<#
  OMS360 launcher.
    ./start.ps1        installs on first run, builds the UI, serves everything at http://127.0.0.1:8000
    ./start.ps1 -Dev   API on :8000 with reload + Vite dev server on http://localhost:5173
#>
param([switch]$Dev)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$py = Join-Path $root "backend\.venv\Scripts\python.exe"

if (-not (Test-Path $py)) {
    Write-Host "Creating Python virtual environment..."
    python -m venv (Join-Path $root "backend\.venv")
    & $py -m pip install -q -r (Join-Path $root "backend\requirements.txt")
}
if (-not (Test-Path (Join-Path $root "frontend\node_modules"))) {
    Write-Host "Installing frontend packages..."
    Push-Location (Join-Path $root "frontend"); npm install --no-fund --no-audit; Pop-Location
}

if ($Dev) {
    Start-Process -FilePath $py -ArgumentList "-m uvicorn app.main:app --reload --port 8000" -WorkingDirectory (Join-Path $root "backend")
    Push-Location (Join-Path $root "frontend"); npm run dev; Pop-Location
} else {
    Push-Location (Join-Path $root "frontend"); npm run build; Pop-Location
    Write-Host "OMS360 running at http://127.0.0.1:8000  (Ctrl+C to stop)"
    Push-Location (Join-Path $root "backend"); & $py -m uvicorn app.main:app --port 8000; Pop-Location
}
