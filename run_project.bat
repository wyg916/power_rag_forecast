@echo off
chcp 65001 >nul
setlocal

pushd "%~dp0"

set "PYTHONUTF8=1"
set "RC_NO_PAUSE=0"
if "%NO_PAUSE%"=="1" set "RC_NO_PAUSE=1"
set "TEMP=%~dp0.codex_tmp\rc_runtime_tmp"
set "TMP=%TEMP%"
if not exist "%TEMP%" mkdir "%TEMP%"
for /f "delims=" %%I in ('git -C "%~dp0." rev-parse --git-common-dir 2^>nul') do set "GIT_COMMON_DIR=%%I"
for %%I in ("%GIT_COMMON_DIR%") do set "GIT_COMMON_DIR=%%~fI"
if not exist "%GIT_COMMON_DIR%\HEAD" (
    echo [ERROR] Git common directory could not be resolved.
    goto end_error
)
for %%I in ("%GIT_COMMON_DIR%\..") do set "SHARED_PROJECT_ROOT=%%~fI"
echo [INFO] Git common worktree: %SHARED_PROJECT_ROOT%
if defined PYTHON_EXE if exist "%PYTHON_EXE%" goto runtime_config
set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if exist "%PYTHON_EXE%" goto runtime_config
set "PYTHON_EXE=%SHARED_PROJECT_ROOT%\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    echo [ERROR] Approved E-drive project Python runtime was not found.
    echo [TIP] Set PYTHON_EXE to the approved project virtual environment.
    if "%RC_NO_PAUSE%"=="0" pause
    goto end_error
)

:runtime_config
if not defined LOCAL_RUNTIME_CONFIG if exist "%~dp0.env" set "LOCAL_RUNTIME_CONFIG=%~dp0.env"
if not defined LOCAL_RUNTIME_CONFIG if exist "%SHARED_PROJECT_ROOT%\.env" set "LOCAL_RUNTIME_CONFIG=%SHARED_PROJECT_ROOT%\.env"
if not defined LOCAL_RUNTIME_CONFIG (
    echo [ERROR] Local runtime config was not found.
    echo [TIP] Set LOCAL_RUNTIME_CONFIG to an E-drive, Git-ignored env file.
    if "%RC_NO_PAUSE%"=="0" pause
    goto end_error
)
if not defined LOCAL_DATABASE_CONFIG if exist "%SHARED_PROJECT_ROOT%_本地配置\beta10d_day4_runtime.env" set "LOCAL_DATABASE_CONFIG=%SHARED_PROJECT_ROOT%_本地配置\beta10d_day4_runtime.env"
if not defined LOCAL_DATABASE_CONFIG (
    echo [ERROR] Least-privilege database identity config was not found.
    echo [TIP] Set LOCAL_DATABASE_CONFIG to the approved E-drive Day 4 identity file.
    if "%RC_NO_PAUSE%"=="0" pause
    goto end_error
)
set "RC_JWT_SECRET_FILE=%~dp0.codex_tmp\rc_runtime_jwt.secret"
if exist "%RC_JWT_SECRET_FILE%" goto jwt_secret_ready
"%PYTHON_EXE%" -c "import pathlib,secrets; pathlib.Path(r'%RC_JWT_SECRET_FILE%').write_text(secrets.token_urlsafe(48), encoding='utf-8')"
if errorlevel 1 goto end_error
:jwt_secret_ready
set /p JWT_SECRET_KEY=<"%RC_JWT_SECRET_FILE%"
if not defined JWT_SECRET_KEY goto jwt_secret_error
goto jwt_secret_complete
:jwt_secret_error
echo [ERROR] Local JWT signing secret could not be loaded.
goto end_error
:jwt_secret_complete
if not defined QDRANT_RUNTIME_CONFIG if exist "%SHARED_PROJECT_ROOT%_运行资产\rag-r1\qdrant\secrets\runtime.env" set "QDRANT_RUNTIME_CONFIG=%SHARED_PROJECT_ROOT%_运行资产\rag-r1\qdrant\secrets\runtime.env"
if not defined QDRANT_RUNTIME_CONFIG (
    echo [ERROR] Approved Qdrant runtime config was not found.
    echo [TIP] Set QDRANT_RUNTIME_CONFIG to the approved E-drive RAG-R1 runtime.env.
    if "%RC_NO_PAUSE%"=="0" pause
    goto end_error
)

if /I "%~1"=="menu" goto menu
goto rcstart

:rcstart
cls
echo ==========================================================
echo  Power Trading AI Platform - Unified RC One-click Launcher
echo ==========================================================
for /f "delims=" %%I in ('git -C "%~dp0." branch --show-current 2^>nul') do set "RC_BRANCH=%%I"
for /f "delims=" %%I in ('git -C "%~dp0." rev-parse HEAD 2^>nul') do set "RC_SHA=%%I"
echo [INFO] RC branch: %RC_BRANCH%
echo [INFO] RC SHA: %RC_SHA%
echo [INFO] Logs: %~dp0output\runtime_logs
echo.

"%PYTHON_EXE%" -X utf8 "%~dp0scripts\web_platform_launcher.py" --runtime-config "%LOCAL_DATABASE_CONFIG%" --runtime-config "%LOCAL_RUNTIME_CONFIG%" --preflight-only
if errorlevel 1 goto rc_failed

if not exist "%~dp0frontend\node_modules" (
    if not exist "%SHARED_PROJECT_ROOT%\frontend\node_modules" (
        echo [ERROR] Approved frontend dependencies were not found.
        echo [TIP] Provision dependencies explicitly before starting the RC; automatic network install is disabled.
        set "RC_EXIT_CODE=2"
        goto rc_failed
    )
    mklink /J "%~dp0frontend\node_modules" "%SHARED_PROJECT_ROOT%\frontend\node_modules" >nul
    if errorlevel 1 (
        echo [ERROR] Failed to reuse the approved frontend dependencies.
        set "RC_EXIT_CODE=2"
        goto rc_failed
    )
    echo [OK] Reused approved frontend dependencies from the Git common worktree.
)

"%PYTHON_EXE%" -X utf8 "%~dp0scripts\phase4_precheck_runtime.py" --runtime-config "%LOCAL_DATABASE_CONFIG%" --runtime-config "%LOCAL_RUNTIME_CONFIG%" redis start
if errorlevel 1 goto rc_failed

"%PYTHON_EXE%" -X utf8 "%~dp0scripts\rag_r1_qdrant_preflight.py" --env-file "%QDRANT_RUNTIME_CONFIG%" --require-assets --require-runtime
if errorlevel 1 goto rc_failed

docker compose --env-file "%QDRANT_RUNTIME_CONFIG%" -f "%~dp0deploy\rag-r1\docker-compose.qdrant.yml" --profile rag-r1-qdrant up -d qdrant
if errorlevel 1 goto rc_failed

set /a QDRANT_PROBE_ATTEMPT=0
:qdrant_probe_retry
set /a QDRANT_PROBE_ATTEMPT+=1
"%PYTHON_EXE%" -X utf8 "%~dp0scripts\rag_r1_qdrant_runtime_probe.py" --env-file "%QDRANT_RUNTIME_CONFIG%" --output "%~dp0output\runtime_logs\qdrant_runtime_probe.json"
if not errorlevel 1 goto qdrant_ready
if %QDRANT_PROBE_ATTEMPT% GEQ 12 goto rc_failed
echo [WAIT] Qdrant is still recovering, retry %QDRANT_PROBE_ATTEMPT%/12...
"%PYTHON_EXE%" -c "import time; time.sleep(5)"
goto qdrant_probe_retry
:qdrant_ready

"%PYTHON_EXE%" -X utf8 "%~dp0scripts\phase4_precheck_runtime.py" --runtime-config "%LOCAL_DATABASE_CONFIG%" --runtime-config "%LOCAL_RUNTIME_CONFIG%" celery start
if errorlevel 1 goto rc_failed

set "NO_PAUSE=1"
call run_web_platform.bat
if errorlevel 1 goto rc_failed

"%PYTHON_EXE%" -X utf8 "%~dp0scripts\phase4_precheck_runtime.py" --runtime-config "%LOCAL_DATABASE_CONFIG%" --runtime-config "%LOCAL_RUNTIME_CONFIG%" combined health
if errorlevel 1 goto rc_failed

echo.
echo [DONE] Unified RC base services are healthy.
echo [INFO] Frontend: http://127.0.0.1:5173
echo [INFO] Backend health: http://127.0.0.1:8000/api/health
echo [INFO] Qdrant: https://127.0.0.1:6333 ^(TLS + API key^)
echo [INFO] Use "run_project.bat menu" for maintenance actions.
if "%RC_NO_PAUSE%"=="0" pause
goto end

:rc_failed
if not defined RC_EXIT_CODE set "RC_EXIT_CODE=%ERRORLEVEL%"
echo.
echo [ERROR] Unified RC startup failed, exit code: %RC_EXIT_CODE%.
echo [TIP] Inspect output\runtime_logs and output\runtime_logs\phase4.
if "%RC_NO_PAUSE%"=="0" pause
popd
exit /b %RC_EXIT_CODE%

:menu
cls
echo ================================================
echo  Power Trading AI Platform - Maintenance Menu v2.11.2
echo ================================================
echo.
echo  1. Start/reuse unified RC base services
echo  2. Run daily refresh and fast forecast
echo  3. Run health check
echo  4. Run model auto optimize
echo  5. Run Web smoke test
echo  6. Start desktop GUI
echo  7. Sync core data to database
echo  8. Docker Compose enterprise deploy and smoke test
echo  9. Run timeout-aware baseline tests
echo  Q. Quit
echo.
choice /c 123456789Q /n /m "Select action: "
set "CHOICE_CODE=%ERRORLEVEL%"

if "%CHOICE_CODE%"=="10" goto end
if "%CHOICE_CODE%"=="1" goto web
if "%CHOICE_CODE%"=="2" goto daily
if "%CHOICE_CODE%"=="3" goto health
if "%CHOICE_CODE%"=="4" goto optimize
if "%CHOICE_CODE%"=="5" goto webtest
if "%CHOICE_CODE%"=="6" goto gui
if "%CHOICE_CODE%"=="7" goto syncdb
if "%CHOICE_CODE%"=="8" goto docker
if "%CHOICE_CODE%"=="9" goto tests
goto menu

:web
goto rcstart

:daily
set NO_PAUSE=1
call run_daily_pipeline_refresh_fast_forecast.bat
goto done

:health
set NO_PAUSE=1
call run_health_check.bat
goto done

:optimize
set NO_PAUSE=1
call run_model_auto_optimize.bat
goto done

:webtest
set NO_PAUSE=1
call run_web_smoke_test.bat
goto done

:gui
set NO_PAUSE=1
call run_desktop_gui.bat
goto done

:syncdb
set "PYTHONUTF8=1"
"%PYTHON_EXE%" -X utf8 "%~dp013_sync_core_data_to_db.py"
goto done

:docker
set NO_PAUSE=1
call run_docker_enterprise.bat
goto done

:tests
set NO_PAUSE=1
call run_tests.bat
goto done

:done
echo.
echo [DONE] Operation completed or started.
if "%RC_NO_PAUSE%"=="0" pause
goto menu

:end
popd
exit /b 0

:end_error
popd
exit /b 2


