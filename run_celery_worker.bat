@echo off
chcp 65001 >nul
setlocal

pushd "%~dp0"

set "PYTHONUTF8=1"
set "TEMP=%~dp0.codex_tmp\phase4_runtime_tmp"
set "TMP=%TEMP%"
if not exist "%TEMP%" mkdir "%TEMP%"
set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    echo [ERROR] Project virtual environment is missing: %PYTHON_EXE%
    echo [ERROR] Refusing to fall back to a C-drive or global Python runtime.
    popd
    exit /b 2
)

echo [INFO] Starting isolated Celery health worker.
"%PYTHON_EXE%" -X utf8 "%~dp0scripts\phase4_precheck_runtime.py" celery start

set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
    echo [ERROR] Celery worker exited with code %EXIT_CODE%.
    echo [TIP] Run run_redis_local.bat first and inspect output\runtime_logs\phase4.
)

if not "%NO_PAUSE%"=="1" pause
popd
exit /b %EXIT_CODE%
