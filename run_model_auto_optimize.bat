@echo off

chcp 65001 >nul

setlocal

cd /d "%~dp0"

set "PYTHONUTF8=1"

set "PYTHON_EXE=C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe"

if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

echo [INFO] v2.11.0：模型自优化，回填真实值、更新误差记忆、判断是否需要重训。
"%PYTHON_EXE%" -X utf8 "%~dp0main_daily_run.py" --model-auto-optimize

set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (

    echo.

    echo [ERROR] 模型自优化执行失败，退出码：%EXIT_CODE%

    echo [TIP] 可先运行 run_health_check.bat，并确认数据库可用。

    if not "%NO_PAUSE%"=="1" pause

    exit /b %EXIT_CODE%

)

echo.

echo [DONE] 模型自优化执行完成。

if not "%NO_PAUSE%"=="1" pause

exit /b 0





