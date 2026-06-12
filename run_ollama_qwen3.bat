@echo off
chcp 65001 >nul
setlocal

echo [INFO] v2.11.0: check and start Ollama local model service, prefer qwen3.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_ollama_qwen3.ps1"

set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
    if not "%NO_PAUSE%"=="1" pause
    exit /b %EXIT_CODE%
)

if not "%NO_PAUSE%"=="1" pause
exit /b 0

