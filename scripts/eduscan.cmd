@echo off
setlocal
set "ACTION=%~1"
if "%ACTION%"=="" set "ACTION=start"
if not "%~2"=="" goto usage
if /i "%ACTION%"=="start" goto run
if /i "%ACTION%"=="restart" goto run

goto usage

:usage
echo Usage: %~nx0 [start^|restart]
exit /b 2

:run
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0manage-eduscan.ps1" -Action "%ACTION%"
exit /b %ERRORLEVEL%