@echo off

chcp 65001 >nul

setlocal

cd /d "%~dp0"

set "PYTHONUTF8=1"

set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

if not exist "%~dp0.env" (

    echo [WARN] 未找到 .env，将优先尝试本地文件模式；PJM 刷新需要 PJM_SUBSCRIPTION_KEY，快速预测需要 Active 模型。

)

echo [INFO] v2.11.0：刷新数据 + 快速预测模式，刷新后加载 Active 模型，不重新训练。
"%PYTHON_EXE%" -X utf8 "%~dp0main_daily_run.py" --refresh-data --fast-forecast

set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (

    echo.

    echo [ERROR] 刷新数据 + 快速预测流程执行失败，退出码：%EXIT_CODE%

    echo [TIP] 可先运行 run_health_check.bat，并确认已有可用 Active 模型。

    if not "%NO_PAUSE%"=="1" pause

    exit /b %EXIT_CODE%

)

echo.

echo [DONE] 刷新数据 + 快速预测流程执行完成。

if not "%NO_PAUSE%"=="1" pause

exit /b 0





