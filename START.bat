@echo off
rem A Loot Radar update may have left a newer copy of this file; switch to it and start over.
if exist "%~dp0START.bat.new" (copy /y "%~dp0START.bat.new" "%~f0" >nul & del "%~dp0START.bat.new" & "%~f0" %*)
title Loot Radar
cd /d "%~dp0app"
if exist ".venv\Scripts\pythonw.exe" goto :run

rem ---- find Python 3.10+ ---------------------------------------------------
set "PY="
where py >nul 2>nul && (py -3 -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>nul && set "PY=py -3")
if not defined PY (
  where python >nul 2>nul && (python -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>nul && set "PY=python")
)
if not defined PY (
  echo.
  echo  Loot Radar needs Python, which isn't installed yet.
  echo  Press any key to install it now with winget ^(Windows' built-in installer^),
  echo  or close this window and install it from https://www.python.org/downloads/
  echo  ^(tick "Add python.exe to PATH" in the installer^).
  pause >nul
  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
  echo.
  echo  Python installed. Close this window and double-click START.bat again.
  pause
  exit /b
)

rem ---- first run: create a private Python environment and install packages ----
if not exist ".venv\Scripts\pythonw.exe" (
  echo  First run: setting things up ^(takes a minute or two^)...
  %PY% -m venv .venv || goto :fail
  ".venv\Scripts\python.exe" -m pip install --upgrade pip -q
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt -q || goto :fail
  echo  Done. Loot Radar now runs in the system tray ^(the ^^ icons next to the clock^).
  timeout /t 4 >nul
)

:run
rem "START.bat console" runs it in this window with the log visible (for troubleshooting).
if /i "%~1"=="console" (
  ".venv\Scripts\python.exe" launcher.py --console
  pause
  exit /b
)

rem Install anything new (shown here), clear a stuck earlier start, then run without a window.
".venv\Scripts\python.exe" launcher.py --prepare
if errorlevel 1 (
  pause
  exit /b
)
start "" ".venv\Scripts\pythonw.exe" launcher.py %*
exit /b

:fail
echo.
echo  Setup failed. Take a screenshot of this window and ask for help.
pause
