@echo off
setlocal
pushd "%~dp0"

set "GUI_BAT="
for /f "delims=" %%G in ('dir /b /a:-d /o:-d "*GUI.bat" 2^>nul') do (
    if not defined GUI_BAT set "GUI_BAT=%%G"
)

if not defined GUI_BAT (
    echo [ERROR] Desktop GUI launcher was not found.
    if not "%NO_PAUSE%"=="1" pause
    popd
    exit /b 1
)

echo [INFO] Start desktop GUI: %GUI_BAT%
call "%GUI_BAT%"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%NO_PAUSE%"=="1" pause
popd
exit /b %EXIT_CODE%
