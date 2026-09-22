# Startup helper (PowerShell)
# Usage: .\start.ps1
\Continue = 'Stop'
Set-Location (Join-Path \ 'backend')

if (-not (Test-Path '.venv')) {
    Write-Host 'Creating virtualenv...'
    python -m venv .venv
}

\ = Join-Path \ 'backend\.venv\Scripts\python.exe'

if (-not (Test-Path \)) {
    \ = 'python'
}

Write-Host 'Installing dependencies (first run)...'
& \ -m pip install -q -r requirements.txt

Write-Host 'Starting Resume Agent on http://localhost:8000'
& \ -m uvicorn app.main:app --host 127.0.0.1 --port 8000
