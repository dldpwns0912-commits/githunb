@echo off
chcp 65001 > nul
title GitHub Upload
cd /d "%~dp0"

set "PATH=%USERPROFILE%\.git_portable\cmd;%USERPROFILE%\.git_portable\mingw64\bin;%PATH%"

echo ============================================================
echo   [GitHub 업로드] SANABI Custom Controller
echo ============================================================
echo.
echo [1/2] GitHub 인증을 시작합니다 (브라우저가 열립니다)...
call git-credential-manager github login --browser

echo.
echo [2/2] GitHub 저장소로 파일을 전송(Push)합니다...
git push -u origin main

echo.
echo ============================================================
if errorlevel 1 (
    echo [!] 업로드 중 오류가 발생했습니다.
) else (
    echo [OK] GitHub에 성공적으로 업로드되었습니다!
)
echo ============================================================
echo.
pause
