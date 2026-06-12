@echo off
setlocal
cd /d "%~dp0"

set "PYTHONUTF8=1"
set "PYTHON_EXE=C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

echo [INFO] v2.11.0: run project health check.

if "%START_OLLAMA%"=="1" (
    set "PREVIOUS_NO_PAUSE=%NO_PAUSE%"
    set "NO_PAUSE=1"
    call "%~dp0run_ollama_qwen3.bat"
    set "NO_PAUSE=%PREVIOUS_NO_PAUSE%"
    if errorlevel 1 (
        echo [WARN] Ollama/qwen3 local model check failed. Continue health check with fallback.
    )
) else (
    echo [INFO] Skip Ollama/qwen3 check. Set START_OLLAMA=1 to enable it.
)

"%PYTHON_EXE%" -X utf8 "%~dp009_health_check.py"
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
    echo.
    echo [ERROR] Health check failed, exit code: %EXIT_CODE%
    if not "%NO_PAUSE%"=="1" pause
    exit /b %EXIT_CODE%
)

echo.
echo [DONE] Health check completed.
if not "%NO_PAUSE%"=="1" pause
exit /b 0


