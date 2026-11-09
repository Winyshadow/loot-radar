@echo off
rem A Loot Radar update may have left a newer copy of this file; switch to it and start over.
if exist "%~dp0START.bat.new" (copy /y "%~dp0START.bat.new" "%~f0" >nul & del "%~dp0START.bat.new" & "%~f0" %*)
title Loot Radar
cd /d "%~dp0app"

rem Python 3.10 to 3.14: one of Loot Radar's parts (aiohttp) has no ready-made download for newer ones yet.
set "OK=import sys; sys.exit(0 if (3,10)<=sys.version_info[:2]<=(3,14) else 1)"

rem A private environment built with a Python that's too new (or since removed) can't install the parts: rebuild it.
if exist ".venv" (
  ".venv\Scripts\python.exe" -c "%OK%" >nul 2>nul <nul || (
    echo  Rebuilding Loot Radar's Python setup with a supported Python version...
    rmdir /s /q ".venv" 2>nul
    if exist ".venv" (
      echo  Couldn't remove the old setup. Quit Loot Radar ^(tray icon^), then run START.bat again.
      pause
      exit /b
    )
  )
)
if exist ".venv\Scripts\pythonw.exe" goto :run

rem ---- find Python 3.10 to 3.14 ----------------------------------------------
call :find
if defined PY goto :setup
echo.
echo  Loot Radar needs Python 3.10 to 3.14 ^(Python 3.15 and newer is too new for one of its parts^).
echo  Press any key to install Python 3.12 now with winget ^(Windows' built-in installer^).
echo  Any other Python you already have stays installed.
echo  Or close this window and install Python 3.12 from https://www.python.org/downloads/
echo  ^(tick "Add python.exe to PATH" in the installer^).
pause >nul
winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
call :find
if defined PY goto :setup
echo.
echo  Python installed. Close this window and double-click START.bat again.
pause
exit /b

:setup
rem ---- first run: create a private Python environment and install packages ----
echo  First run: setting things up ^(takes a minute or two^)...
%PY% -m venv .venv || goto :fail
".venv\Scripts\python.exe" -m pip install --upgrade pip -q
".venv\Scripts\python.exe" -m pip install -r requirements.txt -q || goto :fail
echo  Done. Loot Radar now runs in the system tray ^(the ^^ icons next to the clock^).
timeout /t 4 >nul

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
exit /b

rem ---- helpers ------------------------------------------------------------------
:find
rem Sets PY to the first Python 3.10-3.14 found: the py launcher, then the usual install folders, then PATH.
set "PY="
for %%V in (3.12 3.13 3.14 3.11 3.10) do if not defined PY call :try py -%%V
for %%V in (312 313 314 311 310) do if not defined PY call :try "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
for %%V in (312 313 314 311 310) do if not defined PY call :try "%ProgramFiles%\Python%%V\python.exe"
for %%V in (3.12 3.13 3.14 3.11 3.10) do if not defined PY call :try "%LOCALAPPDATA%\Python\pythoncore-%%V-64\python.exe"
if not defined PY call :try python
exit /b

:try
rem <nul: never sit waiting on a hidden "install this version?" question from the py launcher.
%* -c "%OK%" >nul 2>nul <nul && set "PY=%*"
exit /b
