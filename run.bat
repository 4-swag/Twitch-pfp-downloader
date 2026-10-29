@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

REM The bare "python" command on this machine is the Windows Store stub; find a real one.
set "PY=%LOCALAPPDATA%\Python\bin\python.exe"
if not exist "%PY%" set "PY=py -3"

if not exist ".venv\Scripts\python.exe" (
    echo [setup] creating virtual environment...
    %PY% -m venv .venv || goto :err
    echo [setup] installing dependencies...
    ".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :err
)

set "ARGS=%*"
if "%ARGS%"=="" (
    echo Enter one or more Twitch usernames or twitch.tv URLs, separated by spaces
    set /p "ARGS=> "
)

".venv\Scripts\python.exe" main.py !ARGS!
set "CODE=!ERRORLEVEL!"
if not "!CODE!"=="0" (
    echo.
    echo [exit code !CODE!]
)
echo.
pause
exit /b !CODE!

:err
echo.
echo [setup failed] see messages above.
pause
exit /b 1
