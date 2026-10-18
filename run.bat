@echo off
title Social Glitch
echo ====================================
echo       SOCIAL GLITCH - START
echo ====================================
echo.

where gcc >nul 2>nul
if errorlevel 1 (
    echo GCC was not found in PATH.
    echo Install MinGW/MSYS2 and make sure gcc is available.
    pause
    exit /b 1
)

if not exist social_glitch_server.exe (
    echo Compiling C backend...
    gcc server.c -o social_glitch_server.exe -lws2_32
    if errorlevel 1 (
        echo.
        echo Backend compilation failed.
        pause
        exit /b 1
    )
)

start "Social Glitch C Backend" cmd /k social_glitch_server.exe

timeout /t 1 /nobreak >nul

echo Starting Python frontend...
python social_glitch.py
pause
