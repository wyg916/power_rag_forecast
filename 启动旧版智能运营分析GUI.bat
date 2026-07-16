@echo off

chcp 65001 >nul

setlocal

cd /d "%~dp0"

set "PYTHONUTF8=1"

set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

echo [INFO] 启动旧版 Tkinter GUI fallback。

"%PYTHON_EXE%" -X utf8 "%~dp0gui_launcher.py"

set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (

    echo.

    echo [ERROR] 旧版 GUI 启动失败，退出码：%EXIT_CODE%

    if not "%NO_PAUSE%"=="1" pause

    exit /b %EXIT_CODE%

)

echo.

echo [DONE] 旧版 GUI 已退出。

if not "%NO_PAUSE%"=="1" pause

exit /b 0

