@echo off

chcp 65001 >nul

setlocal

cd /d "%~dp0"

set "PYTHONUTF8=1"

set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

if not exist "%~dp0.env" (

    echo [WARN] 未找到 .env，将优先尝试本地文件模式；快速预测需要已有 Active 模型。

)

echo [INFO] v2.9.1：快速预测模式，加载 Active 模型，不重新训练。
"%PYTHON_EXE%" -X utf8 "%~dp0main_daily_run.py" --fast-forecast

set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (

    echo.

    echo [ERROR] 快速预测流程执行失败，退出码：%EXIT_CODE%

    echo [TIP] 若提示没有 Active 模型，请先运行 run_daily_pipeline_retrain_model.bat 并在模型中心设为 Active。

    if not "%NO_PAUSE%"=="1" pause

    exit /b %EXIT_CODE%

)

echo.

echo [DONE] 快速预测流程执行完成。

if not "%NO_PAUSE%"=="1" pause

exit /b 0





