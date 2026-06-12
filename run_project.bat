@echo off
setlocal

pushd "%~dp0"

:menu
cls
echo ================================================
echo  Power Trading AI Platform - Core Launcher v2.11.2
echo ================================================
echo.
echo  1. Restart Web platform with latest UI
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
set NO_PAUSE=1
call run_web_platform.bat
goto done

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
set "PYTHON_EXE=C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"
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
pause
goto menu

:end
popd
exit /b 0


