@echo off
chcp 65001 >nul
setlocal
pushd "%~dp0"

set "PYTHONUTF8=1"
if defined NODE_HOME if exist "%NODE_HOME%\node.exe" set "PATH=%NODE_HOME%;%PATH%"
if defined NODE_HOME if exist "%NODE_HOME%\npm.cmd" set "NPM_EXE=%NODE_HOME%\npm.cmd"
for /f "delims=" %%I in ('git -C "%~dp0." rev-parse --git-common-dir 2^>nul') do set "GIT_COMMON_DIR=%%I"
for %%I in ("%GIT_COMMON_DIR%") do set "GIT_COMMON_DIR=%%~fI"
if not exist "%GIT_COMMON_DIR%\HEAD" (
    echo [ERROR] Git common directory could not be resolved.
    popd
    exit /b 2
)
for %%I in ("%GIT_COMMON_DIR%\..") do set "SHARED_PROJECT_ROOT=%%~fI"
if defined PYTHON_EXE if exist "%PYTHON_EXE%" goto python_ready
set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if exist "%PYTHON_EXE%" goto python_ready
set "PYTHON_EXE=%SHARED_PROJECT_ROOT%\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    echo [ERROR] Approved E-drive project Python runtime was not found.
    echo [TIP] Set PYTHON_EXE to the approved project virtual environment.
    popd
    exit /b 2
)

:python_ready
if not defined LOCAL_RUNTIME_CONFIG if exist "%~dp0.env" set "LOCAL_RUNTIME_CONFIG=%~dp0.env"
if not defined LOCAL_RUNTIME_CONFIG if exist "%SHARED_PROJECT_ROOT%\.env" set "LOCAL_RUNTIME_CONFIG=%SHARED_PROJECT_ROOT%\.env"
if not defined LOCAL_RUNTIME_CONFIG (
    echo [ERROR] Local runtime config was not found.
    echo [TIP] Set LOCAL_RUNTIME_CONFIG to an E-drive, Git-ignored env file.
    popd
    exit /b 2
)
if not defined LOCAL_DATABASE_CONFIG if exist "%SHARED_PROJECT_ROOT%_本地配置\beta10d_day4_runtime.env" set "LOCAL_DATABASE_CONFIG=%SHARED_PROJECT_ROOT%_本地配置\beta10d_day4_runtime.env"
if not defined LOCAL_DATABASE_CONFIG (
    echo [ERROR] Least-privilege database identity config was not found.
    echo [TIP] Set LOCAL_DATABASE_CONFIG to the approved E-drive Day 4 identity file.
    popd
    exit /b 2
)
if not defined RAG_PREPRODUCTION_CONFIG set "RAG_PREPRODUCTION_CONFIG=%~dp0deploy\rag-r1\preproduction-profile.env"
if not exist "%RAG_PREPRODUCTION_CONFIG%" (
    echo [ERROR] Git-controlled RAG preproduction profile was not found.
    popd
    exit /b 2
)
rem RAG_READER_CONFIG is validated by web_platform_launcher.py; keep batch parsing
rem independent from non-ASCII paths and fail closed in the Python preflight.
if not exist "%~dp0frontend\node_modules" (
    if not exist "%SHARED_PROJECT_ROOT%\frontend\node_modules" (
        echo [ERROR] Approved frontend dependencies were not found.
        echo [TIP] Provision dependencies explicitly before starting the RC; automatic network install is disabled.
        popd
        exit /b 2
    )
    mklink /J "%~dp0frontend\node_modules" "%SHARED_PROJECT_ROOT%\frontend\node_modules" >nul
    if errorlevel 1 (
        echo [ERROR] Failed to reuse the approved frontend dependencies.
        popd
        exit /b 2
    )
    echo [OK] Reused approved frontend dependencies from the Git common worktree.
)

echo [INFO] Unified RC Web launcher: reuse healthy services and start missing services.
if not defined WEB_BACKEND_PORT set "WEB_BACKEND_PORT=8000"
if not defined WEB_FRONTEND_PORT set "WEB_FRONTEND_PORT=5173"
echo [INFO] Frontend: http://127.0.0.1:%WEB_FRONTEND_PORT%
echo [INFO] Backend docs: http://127.0.0.1:%WEB_BACKEND_PORT%/docs
echo [INFO] Database writes are disabled during launcher startup; data preparation is explicit.
echo [INFO] Ollama warmup is skipped by default. Set START_OLLAMA=1 only when memory is enough.
echo.

set "WEB_LAUNCHER_BROWSER_ARG="
if "%NO_BROWSER%"=="1" set "WEB_LAUNCHER_BROWSER_ARG=--no-browser"
"%PYTHON_EXE%" -X utf8 "%~dp0scripts\web_platform_launcher.py" --runtime-config "%RAG_PREPRODUCTION_CONFIG%" --runtime-config "%LOCAL_DATABASE_CONFIG%" --runtime-config "%LOCAL_RUNTIME_CONFIG%" --skip-sync %WEB_LAUNCHER_BROWSER_ARG%
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
