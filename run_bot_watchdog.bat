@echo off
title Bot Watchdog
cd /d C:\yobit_bot
:loop
tasklist /FI "WINDOWTITLE eq Crypto Bot*" 2>nul | find /I "pythonw.exe" >nul
if errorlevel 1 (
    echo [%date% %time%] Bot not running, starting...
    start "" pythonw.exe C:\yobit_bot\bot.py
) else (
    echo [%date% %time%] Bot is running
)
timeout /t 60 /nobreak >nul
goto loop