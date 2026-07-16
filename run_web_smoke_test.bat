@echo off
setlocal

pushd "%~dp0"

set "PYTHONUTF8=1"
set "LOCAL_LLM_SUMMARY_ENABLED=0"
set "DIFY_ENABLED=0"
set "LLM_AUTO_PULL=0"
set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

echo [INFO] v2.11.2 DB-STATE-V1: run Web platform smoke test.
echo [INFO] Frontend TypeScript/Vite build check.
pushd "%~dp0frontend"
call npm run build
set "FRONTEND_BUILD_CODE=%ERRORLEVEL%"
popd
if not "%FRONTEND_BUILD_CODE%"=="0" (
    echo.
    echo [ERROR] Frontend build failed, exit code: %FRONTEND_BUILD_CODE%
    if not "%NO_PAUSE%"=="1" pause
    popd
    exit /b %FRONTEND_BUILD_CODE%
)
echo [DONE] Frontend build passed.
echo [INFO] Core facts, tariff rules and policy summaries sync check.
"%PYTHON_EXE%" -X utf8 "%~dp013_sync_core_data_to_db.py"
if errorlevel 1 (
    echo [ERROR] Core data sync failed.
    if not "%NO_PAUSE%"=="1" pause
    popd
    exit /b 1
)
echo [INFO] Backend API tests.

if "%START_OLLAMA%"=="1" (
    set "PREVIOUS_NO_PAUSE=%NO_PAUSE%"
    set "NO_PAUSE=1"
    call "%~dp0run_ollama_qwen3.bat"
    set "NO_PAUSE=%PREVIOUS_NO_PAUSE%"
    if errorlevel 1 (
        echo [WARN] Ollama/qwen3 local model check failed. Continue Web smoke test with fallback.
    )
) else (
    echo [INFO] Skip Ollama/qwen3 check in smoke test. Set START_OLLAMA=1 to enable it.
)

"%PYTHON_EXE%" -X utf8 -m pytest tests\test_web_platform.py tests\test_tariff_ai_tools.py -q --durations=10

set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
    echo.
    echo [ERROR] Web platform smoke test failed, exit code: %EXIT_CODE%
    if not "%NO_PAUSE%"=="1" pause
    popd
    exit /b %EXIT_CODE%
)

echo [DONE] Web platform smoke test passed.
if not "%NO_PAUSE%"=="1" pause
popd
exit /b 0


