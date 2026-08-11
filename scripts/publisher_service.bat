@echo off
REM The status publisher, shaped for unattended use by Task Scheduler.
REM
REM Differs from run_publisher.bat in three ways that matter when nobody is
REM watching:
REM
REM   * It calls the venv's python.exe directly instead of activating the venv.
REM     Activation relies on a user environment that a task running as SYSTEM
REM     does not have.
REM   * It uses an absolute working directory derived from its own location, so
REM     it does not care that SYSTEM starts in C:\Windows\System32.
REM   * All output goes to a file, because there is no console to print to.
REM
REM Install with scripts\install_publisher_task.bat -- do not run both this and
REM run_publisher.bat, or two publishers will fight over the same file.

cd /d "%~dp0.."

if not exist "logs" mkdir "logs"

set PYTHON=%~dp0..\.venv\Scripts\python.exe
if not exist "%PYTHON%" set PYTHON=python

:loop
echo [%date% %time%] Starting status publisher... >> "logs\publisher_service.log"
"%PYTHON%" "%~dp0publish_status.py" >> "logs\publisher_service.log" 2>&1
echo [%date% %time%] Publisher exited. Restarting in 60 seconds... >> "logs\publisher_service.log"
timeout /t 60 /nobreak > nul
goto loop
