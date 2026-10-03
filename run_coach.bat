@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python launcher ^(py^) not found.
  echo Install Python 3.10+ and enable Add Python to PATH.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [SETUP] Creating virtual environment...
  py -3 -m venv .venv
  if errorlevel 1 goto :fail
)

echo [SETUP] Installing/updating requirements...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :fail

echo.
echo [START] Auto-detecting USB HDMI Capture...
echo [TIP] Press Q or ESC in the preview window to stop.
echo.
".venv\Scripts\python.exe" realtime_ai_coach.py --device auto --width 1920 --height 1080 --fps 120 --preview

pause
exit /b 0

:fail
echo.
echo [ERROR] Setup failed.
pause
exit /b 1
