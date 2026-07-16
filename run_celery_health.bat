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
    popd
    exit /b 2
)

"%PYTHON_EXE%" -X utf8 "%~dp0scripts\phase4_precheck_runtime.py" combined health
set "EXIT_CODE=%ERRORLEVEL%"
if not "%NO_PAUSE%"=="1" pause
popd
exit /b %EXIT_CODE%
