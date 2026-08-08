@echo off
setlocal
pushd "%~dp0"

set "PYTHONUTF8=1"
set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

echo [INFO] Legacy component wrapper: reuse or start FastAPI backend without data sync.
"%PYTHON_EXE%" -X utf8 "%~dp0scripts\web_platform_launcher.py" --backend-only --no-browser --skip-sync
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo [ERROR] Backend startup failed, exit code: %EXIT_CODE%
    echo [TIP] See output\runtime_logs\web_backend.log
)

if not "%NO_PAUSE%"=="1" pause
popd
exit /b %EXIT_CODE%
