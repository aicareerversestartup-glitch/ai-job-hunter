# Start API (port 8000) and UI (port 5173) for local use on Windows.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
$api = Start-Process -PassThru -NoNewWindow .\.venv\Scripts\python.exe -ArgumentList "-m","uvicorn","backend.main:app","--host","127.0.0.1","--port","8000"
try {
  Push-Location frontend
  Start-Process "http://localhost:5173"
  npm run dev
} finally {
  Pop-Location
  Stop-Process -Id $api.Id -ErrorAction SilentlyContinue
}
