@echo off
chcp 65001 > nul
title GitHub Upload
cd /d "%~dp0"

echo ============================================================
echo   [GitHub 업로드] SANABI Custom Controller
echo ============================================================
echo.
echo GitHub에 파일을 전송합니다.
echo 브라우저 로그인 창이 뜨면 로그인을 진행해 주세요.
echo.

"%USERPROFILE%\.git_portable\cmd\git.exe" push -u origin main

echo.
echo ============================================================
if errorlevel 1 (
    echo [!] 업로드 중 오류가 발생했습니다.
) else (
    echo [OK] GitHub에 성공적으로 업로드되었습니다!
)
echo ============================================================
echo 아무 키나 누르면 창이 닫힙니다.
pause > nul
