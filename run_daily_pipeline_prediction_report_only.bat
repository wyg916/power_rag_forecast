@echo off

chcp 65001 >nul

setlocal

cd /d "%~dp0"

set "PYTHONUTF8=1"

set "PYTHON_EXE=C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe"

if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

if not exist "%~dp0.env" (

    echo [WARN] 未找到 .env，将优先尝试本地文件模式；数据库同步会被跳过。

)

echo [INFO] v2.9.1：兼容旧预测并生成 AI 报告模式，会重新预测/训练；快速推理请使用 run_daily_pipeline_fast_forecast.bat。
"%PYTHON_EXE%" -X utf8 "%~dp0main_daily_run.py" --prediction-report-only

set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (

    echo.

    echo [ERROR] 预测并生成报告流程失败，退出码：%EXIT_CODE%

    echo [TIP] 可先运行 run_health_check.bat 查看环境、依赖、数据库和关键文件状态。

    if not "%NO_PAUSE%"=="1" pause

    exit /b %EXIT_CODE%

)

echo.

echo [DONE] 预测并生成报告流程完成。

if not "%NO_PAUSE%"=="1" pause

exit /b 0



