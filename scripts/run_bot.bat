@echo off
REM Runs the trading bot and auto-restarts it if it ever crashes/exits.
REM Put a shortcut to this in the VPS Startup folder (see docs/VPS_DEPLOYMENT.md).

cd /d "%~dp0\.."
call .venv\Scripts\activate

:loop
echo [%date% %time%] Starting bot...
python live_trader.py
echo [%date% %time%] Bot exited. Restarting in 30 seconds... (Ctrl+C to stop)
timeout /t 30 /nobreak
goto loop
