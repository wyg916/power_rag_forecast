@echo off

chcp 65001 >nul

setlocal

cd /d "%~dp0"

set "PYTHONUTF8=1"

set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

if not exist "%~dp0.env" (

    echo [WARN] 未找到 .env，将优先尝试本地文件模式；数据库同步和模型追踪落库会被跳过。

)

echo [INFO] v2.9.1：兼容旧全流程，通过 services 服务层调度 prediction_engine，会重新训练。
"%PYTHON_EXE%" -X utf8 "%~dp0main_daily_run.py"

set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (

    echo.

    echo [ERROR] 全流程执行失败，退出码：%EXIT_CODE%

    echo [TIP] 可先运行 run_health_check.bat 查看环境、依赖、数据库和关键文件状态。

    if not "%NO_PAUSE%"=="1" pause

    exit /b %EXIT_CODE%

)

echo.

echo [DONE] 全流程执行完成。

if not "%NO_PAUSE%"=="1" pause

exit /b 0



