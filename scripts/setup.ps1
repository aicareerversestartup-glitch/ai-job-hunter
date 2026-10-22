# One-time setup on Windows (PowerShell). Run from the project folder:
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$hasPy = [bool](Get-Command py -ErrorAction SilentlyContinue)
$hasPython = [bool](Get-Command python -ErrorAction SilentlyContinue)
if (-not ($hasPy -or $hasPython)) { throw "Install Python 3.11 or newer from python.org (tick 'Add python.exe to PATH'), then run this again." }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw "Install Node.js 20+ from nodejs.org." }

if (-not (Test-Path .venv\Scripts\python.exe)) {
  if ($hasPy) { py -3 -m venv .venv } else { python -m venv .venv }
  if (-not (Test-Path .venv\Scripts\python.exe)) { throw "Could not create the Python environment. Reinstall Python from python.org." }
}
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw "Installing Python packages failed. Check your internet connection and try again." }
& .\.venv\Scripts\python.exe -m playwright install chromium

if (-not (Test-Path .env)) {
  Copy-Item .env.example .env
  $secret = & .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
  (Get-Content .env) -replace '^SECRET_KEY=$', "SECRET_KEY=$secret" | Set-Content .env
  Write-Host "Created .env with a new SECRET_KEY."
}

Push-Location frontend
npm install --no-audit --no-fund
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "npm install failed. Check your internet connection and try again." }
npm run build
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "Building the app screens failed." }
Pop-Location

& .\.venv\Scripts\python.exe -m alembic upgrade head

# Desktop shortcut
try {
  $root = (Get-Location).Path
  $shell = New-Object -ComObject WScript.Shell
  $link = $shell.CreateShortcut([Environment]::GetFolderPath("Desktop") + "\AI Job Hunter.lnk")
  $link.TargetPath = Join-Path $root "Start AI Job Hunter.bat"
  $link.WorkingDirectory = $root
  $link.Save()
  Write-Host "Added an 'AI Job Hunter' shortcut to your Desktop."
} catch { Write-Host "Could not create a Desktop shortcut; use 'Start AI Job Hunter.bat' instead." }
Write-Host ""
Write-Host "Setup complete."
Write-Host "Optional: install Tesseract OCR (github.com/UB-Mannheim/tesseract/wiki) to read scanned PDF CVs."
