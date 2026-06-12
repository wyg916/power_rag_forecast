@echo off
setlocal
pushd "%~dp0"

set "PYTHONUTF8=1"
set "PYTHON_EXE=C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

echo [INFO] v2.11.2 DB-STATE-V1: restart React frontend with latest source.
"%PYTHON_EXE%" -X utf8 "%~dp0scripts\web_platform_launcher.py" --frontend-only --no-browser --restart
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo [ERROR] Frontend startup failed, exit code: %EXIT_CODE%
    echo [TIP] See output\runtime_logs\web_frontend.log
)

if not "%NO_PAUSE%"=="1" pause
popd
exit /b %EXIT_CODE%
