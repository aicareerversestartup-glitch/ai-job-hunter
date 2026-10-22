@echo off
title AI Job Hunter
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo First start: installing AI Job Hunter. This takes a few minutes, only once.
  powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\setup.ps1"
  if errorlevel 1 (
    echo.
    echo Setup did not finish. Read the message above, fix it, then double-click this file again.
    pause
    exit /b 1
  )
)

if not exist "frontend\dist\index.html" (
  echo Building the app screens...
  pushd frontend
  call npm run build
  popd
)

echo.
echo AI Job Hunter is running. Keep this window open while you use it.
echo Close this window to stop the app.
echo.
start "" cmd /c "timeout /t 5 >nul & start http://localhost:8000"
".venv\Scripts\python.exe" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
pause
