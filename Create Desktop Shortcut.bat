@echo off
rem Makes a "Loot Radar" shortcut with the radar icon on your desktop.
set "HERE=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop') + '\Loot Radar.lnk');" ^
  "$s.TargetPath = '%HERE%START.bat';" ^
  "$s.WorkingDirectory = '%HERE%';" ^
  "$s.IconLocation = '%HERE%app\web\loot-radar.ico';" ^
  "$s.WindowStyle = 7;" ^
  "$s.Save()"
echo.
echo  Done - "Loot Radar" is on your desktop. Double-click it to start Loot Radar
echo  or, if it is already running in the tray, to open the dashboard.
pause
