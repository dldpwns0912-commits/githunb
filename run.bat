@echo off
chcp 65001 > nul
title SANABI Custom Controller CLI
cd /d "%~dp0"
python controller.py
if errorlevel 1 (
    echo.
    echo [오류가 발생했습니다. 창을 닫으려면 아무 키나 누르세요.]
    pause > nul
)
