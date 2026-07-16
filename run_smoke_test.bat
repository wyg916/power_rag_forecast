@echo off

chcp 65001 >nul

setlocal

cd /d "%~dp0"

set "PYTHONUTF8=1"

set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

echo [INFO] v2.9.1：运行项目轻量整体自检。
"%PYTHON_EXE%" -X utf8 "%~dp0.\10_smoke_test.py"

set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (

    echo.

    echo [ERROR] 轻量整体自检失败，退出码：%EXIT_CODE%

    if not "%NO_PAUSE%"=="1" pause

    exit /b %EXIT_CODE%

)

echo.

echo [DONE] 轻量整体自检通过。

if not "%NO_PAUSE%"=="1" pause

exit /b 0



