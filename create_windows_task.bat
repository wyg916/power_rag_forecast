@echo off

chcp 65001 >nul

setlocal

cd /d "%~dp0"

set "PYTHONUTF8=1"

if not exist "%~dp0.env" (

    echo [WARN] 未找到 .env，计划任务运行时将优先尝试本地文件模式。

)

echo [INFO] v2.9.1：创建或覆盖 Windows 计划任务，支持快速预测、重训和模型自优化模式。
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0create_windows_task.ps1"

set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (

    echo.

    echo [ERROR] 计划任务创建失败，退出码：%EXIT_CODE%

    if not "%NO_PAUSE%"=="1" pause

    exit /b %EXIT_CODE%

)

echo.

echo [DONE] 计划任务创建完成。

if not "%NO_PAUSE%"=="1" pause

exit /b 0



