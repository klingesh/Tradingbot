@echo off
REM Publishes logs/status.json to a private GitHub repo so the bot can be watched
REM from another machine. Runs SEPARATELY from the bot on purpose: a network call
REM must never be able to delay a trading tick.
REM
REM Put a shortcut to this in the VPS Startup folder alongside run_bot.bat.

cd /d "%~dp0\.."
call .venv\Scripts\activate

:loop
echo [%date% %time%] Starting status publisher...
python scripts\publish_status.py
echo [%date% %time%] Publisher exited. Restarting in 60 seconds... (Ctrl+C to stop)
timeout /t 60 /nobreak
goto loop
