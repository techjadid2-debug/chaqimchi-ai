@echo off
chcp 65001 > nul
title Chaqimchi AI - Ishga Tushirish

if not exist ".venv" (
    echo [OGOHLANTIRISH] Tizim hali o'rnatilmagan.
    echo Avval "install_windows.bat" faylini ishga tushiring.
    pause
    exit /b 1
)

echo ======================================================
echo    Chaqimchi AI ishga tushirilmoqda...
echo ======================================================
echo.

call .venv\Scripts\activate.bat

:: Asosiy Cloud / Web paneli ishga tushirish (Port: 8750)
echo Lokal Web Server: http://localhost:8750
echo Xodimlar Davomat Paneli: http://localhost:8743
echo.
echo Tizimni to'xtatish uchun: Ctrl + C bosing.
echo.

python -m cloud.main
pause
