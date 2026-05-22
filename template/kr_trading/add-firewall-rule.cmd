@echo off
chcp 65001 >nul
REM Optional: only if phone cannot connect. Run as Administrator.
set PORT=8080
if not "%~1"=="" set PORT=%~1
netsh advfirewall firewall add rule name="StockReport HTTP %PORT%" dir=in action=allow protocol=TCP localport=%PORT% profile=private
if %ERRORLEVEL% EQU 0 (echo OK: port %PORT%) else (echo Failed. Right-click this file - Run as administrator.)
pause
