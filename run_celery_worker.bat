@echo off
chcp 65001 >nul
setlocal

pushd "%~dp0"

set "PYTHONUTF8=1"
set "PYTHON_EXE=C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

echo [INFO] Starting Celery worker for async forecast/report/data-sync tasks.
echo [INFO] Redis should be available at REDIS_URL or redis://localhost:6379/0.
"%PYTHON_EXE%" -X utf8 -m celery -A backend.app.workers.celery_app.celery_app worker --pool=solo --loglevel=INFO

set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
    echo [ERROR] Celery worker exited with code %EXIT_CODE%.
    echo [TIP] Install requirements and start Redis, or the API will fall back to local task execution.
)

if not "%NO_PAUSE%"=="1" pause
popd
exit /b %EXIT_CODE%
