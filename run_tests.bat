@echo off
setlocal
pushd "%~dp0"

set "PYTHONUTF8=1"
set "LOCAL_LLM_SUMMARY_ENABLED=0"
set "DIFY_ENABLED=0"
set "START_OLLAMA=0"
set "LLM_AUTO_PULL=0"
set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

echo [INFO] Run timeout-aware baseline test suite.
echo [INFO] Slow AI tests are still executed, but local LLM summary and Dify are disabled for deterministic CI-style runs.

"%PYTHON_EXE%" -X utf8 -m pytest -q
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo [ERROR] Test suite failed, exit code: %EXIT_CODE%
)

if not "%NO_PAUSE%"=="1" pause
popd
exit /b %EXIT_CODE%
