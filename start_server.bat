@echo off
cd /d "%~dp0"
echo [i] Guliz VIP Backend baslatiliyor...
echo [i] Port: 8081
echo [i] Kapatmak icin bu pencereyi kapatin.
echo ========================================
python -u server.py
pause
