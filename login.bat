@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ======================================================
echo Запуск браузера для входа в TikTok через US-прокси...
echo ======================================================
.\venv\Scripts\python.exe login_helper.py
pause
