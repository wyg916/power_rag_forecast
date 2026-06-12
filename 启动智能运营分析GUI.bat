@echo off

chcp 65001 >nul

setlocal

cd /d "%~dp0"

set "PYTHONUTF8=1"

set "PYTHON_EXE=C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe"

if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

if not exist "%~dp0.env" (

    echo [WARN] 未找到 .env，GUI 仍会启动；运行全流程时将优先尝试本地文件模式。

)

echo [INFO] v2.9.1：启动智能运营分析项目现代化控制台（含快速预测、自学习模型中心、预测结果中心和 AI 报告审批流）。
"%PYTHON_EXE%" -X utf8 -m ui.app

set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (

    echo.

    echo [ERROR] 现代化控制台启动失败，退出码：%EXIT_CODE%

    echo [TIP] 可先运行 run_health_check.bat 查看 Python、依赖和路径状态。

    if not "%NO_PAUSE%"=="1" pause

    exit /b %EXIT_CODE%

)

echo.

echo [DONE] 现代化控制台已退出。

if not "%NO_PAUSE%"=="1" pause

exit /b 0



