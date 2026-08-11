@echo off
REM Publishes logs/status.json to a private GitHub repo so the bot can be watched
REM from another machine. Runs SEPARATELY from the bot on purpose: a network call
REM must never be able to delay a trading tick.
REM
REM This needs a console window and stops when it closes or you log off. For a
REM VPS, install it as a scheduled task instead -- it then starts with Windows
REM whether anyone logs in or not:
REM
REM     scripts\install_publisher_task.bat     (from an Admin prompt, once)
REM
REM Don't run both: two publishers writing the same file collide on every push.

cd /d "%~dp0\.."
call .venv\Scripts\activate

:loop
echo [%date% %time%] Starting status publisher...
python scripts\publish_status.py
echo [%date% %time%] Publisher exited. Restarting in 60 seconds... (Ctrl+C to stop)
timeout /t 60 /nobreak
goto loop
