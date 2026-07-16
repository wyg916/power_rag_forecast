@echo off
setlocal
pushd "%~dp0"

set "PYTHONUTF8=1"
if defined NODE_HOME if exist "%NODE_HOME%\node.exe" set "PATH=%NODE_HOME%;%PATH%"
if defined NODE_HOME if exist "%NODE_HOME%\npm.cmd" set "NPM_EXE=%NODE_HOME%\npm.cmd"
set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

echo [INFO] v2.11.2 DB-STATE-V1: restart Web platform with latest source.
echo [INFO] Frontend: http://127.0.0.1:5173
echo [INFO] Backend docs: http://127.0.0.1:8000/docs
echo [INFO] Existing backend/frontend dev processes on ports 8000/5173 will be refreshed.
echo [INFO] Ollama warmup is skipped by default. Set START_OLLAMA=1 only when memory is enough.
echo.

"%PYTHON_EXE%" -X utf8 "%~dp0scripts\web_platform_launcher.py" --restart
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo [ERROR] Web platform startup failed, exit code: %EXIT_CODE%
    echo [TIP] See output\runtime_logs\web_backend.log and output\runtime_logs\web_frontend.log
    if not "%NO_PAUSE%"=="1" pause
    popd
    exit /b %EXIT_CODE%
)

if not "%NO_PAUSE%"=="1" pause
popd
exit /b 0
