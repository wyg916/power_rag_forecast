@echo off
setlocal
pushd "%~dp0"

echo [INFO] Power Trading AI enterprise Docker Compose smoke test.
echo [INFO] Frontend will use http://127.0.0.1:18080
echo [INFO] Backend will use http://127.0.0.1:18000
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\docker_compose_smoke_test.ps1"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo [ERROR] Docker Compose smoke test failed, exit code: %EXIT_CODE%
    if not "%NO_PAUSE%"=="1" pause
    popd
    exit /b %EXIT_CODE%
)

echo [DONE] Docker Compose enterprise stack is ready.
if not "%NO_PAUSE%"=="1" pause
popd
exit /b 0
