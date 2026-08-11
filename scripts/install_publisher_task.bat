@echo off
REM Install the status publisher as a Windows scheduled task.
REM
REM Why a task and not the Startup folder: a Startup shortcut only runs when a
REM user logs in interactively. If the VPS reboots and nobody opens an RDP
REM session, nothing starts -- which is the one situation where remote
REM monitoring matters most. A task registered "at startup" as SYSTEM runs
REM without anyone logging in, and survives you logging off.
REM
REM The trading bot itself still belongs in the Startup folder, because
REM MetaTrader needs an interactive desktop session. The publisher does not: it
REM reads a file and makes an HTTPS request.
REM
REM Run this ONCE, from an Administrator command prompt.

setlocal
set TASKNAME=BeasttStatusPublisher

net session >nul 2>&1
if errorlevel 1 (
    echo.
    echo This needs an Administrator command prompt.
    echo Right-click Command Prompt and choose "Run as administrator", then
    echo run this again.
    echo.
    exit /b 1
)

REM Kept on one line deliberately. Line continuations plus nested quotes are a
REM reliable way to produce a task whose action is subtly wrong, and the failure
REM shows up days later as "why has nothing published".
set RUNME=\"%~dp0publisher_service.bat\"

echo Registering task "%TASKNAME%"...
echo   action: %RUNME%
schtasks /create /tn "%TASKNAME%" /tr "%RUNME%" /sc onstart /ru SYSTEM /rl LIMITED /f
if errorlevel 1 (
    echo.
    echo Failed to register the task. Nothing has been changed.
    exit /b 1
)

echo.
echo Starting it now, so you do not have to reboot...
schtasks /run /tn "%TASKNAME%"

echo.
echo Done. The publisher now starts with Windows, whether anyone logs in or not.
echo.
echo Give it a minute, then check logs\publisher_service.log for a
echo "Published to ..." line. If that file stays empty, run:
echo   schtasks /query /tn "%TASKNAME%" /fo list /v
echo and check the "Task To Run" line points at publisher_service.bat.
echo.
echo   Check it:    schtasks /query /tn "%TASKNAME%"
echo   Its output:  type logs\publisher_service.log
echo   Stop it:     schtasks /end /tn "%TASKNAME%"
echo   Remove it:   schtasks /delete /tn "%TASKNAME%" /f
echo.
echo IMPORTANT: close any run_publisher.bat window, and remove its shortcut from
echo the Startup folder if you added one. Two publishers writing the same file
echo will collide on every push.
echo.
endlocal
