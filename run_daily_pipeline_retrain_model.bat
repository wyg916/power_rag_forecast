@echo off

chcp 65001 >nul

setlocal

cd /d "%~dp0"

set "PYTHONUTF8=1"

set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

if not exist "%~dp0.env" (

    echo [WARN] 未找到 .env，将优先尝试本地文件模式；数据库注册可能被跳过。

)

echo [INFO] v2.9.1：完整重训模式，重新训练并登记 candidate 模型。
"%PYTHON_EXE%" -X utf8 "%~dp0main_daily_run.py" --retrain-model

set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (

    echo.

    echo [ERROR] 完整重训流程执行失败，退出码：%EXIT_CODE%

    echo [TIP] 可先运行 run_health_check.bat 查看环境、依赖、数据库和关键文件状态。

    if not "%NO_PAUSE%"=="1" pause

    exit /b %EXIT_CODE%

)

echo.

echo [DONE] 完整重训流程执行完成，candidate 模型已登记或保存在 model_artifacts。

if not "%NO_PAUSE%"=="1" pause

exit /b 0





