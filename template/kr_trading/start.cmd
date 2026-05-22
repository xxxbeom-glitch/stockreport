@echo off
chcp 65001 >nul
cd /d "%~dp0\..\.."
echo.
echo 스마트폰: PowerShell에서 template\kr_trading\serve-lan.ps1 실행
echo PC만 볼 때: http://127.0.0.1:8080/template/kr_trading/
echo.
python scripts\serve_mock_trading.py --port 8080 --bind 0.0.0.0
