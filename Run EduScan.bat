@echo off
setlocal
set "PROJECT_ROOT=%~dp0"

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_ROOT%scripts\start.ps1" -OpenBrowser
if errorlevel 1 (
  echo.
  echo EduScan could not start. Check the log files in the logs folder.
  pause
)

endlocal
