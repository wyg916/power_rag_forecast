@echo off

chcp 65001 >nul

setlocal

cd /d "%~dp0"

set "PYTHONUTF8=1"

set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

echo [INFO] v2.9.1 模型运维：数据库闭环、真实值回填、误差记忆、退化监控、重训任务登记。
"%PYTHON_EXE%" -X utf8 "%~dp0.\08_sync_database_closure.py"

if not "%ERRORLEVEL%"=="0" goto FAILED

"%PYTHON_EXE%" -X utf8 "%~dp0.\12_update_error_memory.py"

if not "%ERRORLEVEL%"=="0" goto FAILED

"%PYTHON_EXE%" -X utf8 "%~dp0.\06_model_monitor.py"

set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" goto FAILED

echo.

echo [DONE] 模型运维任务完成。

if not "%NO_PAUSE%"=="1" pause

exit /b 0



:FAILED

set "EXIT_CODE=%ERRORLEVEL%"

echo.

echo [ERROR] 模型运维任务失败，退出码：%EXIT_CODE%

if not "%NO_PAUSE%"=="1" pause

exit /b %EXIT_CODE%



