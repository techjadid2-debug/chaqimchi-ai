@echo off
chcp 65001 > nul
title Chaqimchi AI - Ishga Tushirish

cd /d "%~dp0\.."

echo ======================================================
echo    Chaqimchi AI - Do'kon Analitikasi
echo ======================================================
echo.

:: 1. Agar .venv bo'lmasa, avtomatik yaratish
if not exist ".venv" (
    echo [*] Muhit dastlabki sozlanmoqda (bir martalik jarayon)...
    python --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo [OGOHLANTIRISH] Python o'rnatilmagan.
        echo Iltimos, https://www.python.org dan Python 3.11/3.12 ni yuklab o'rnating.
        echo O'rnatishda "Add python.exe to PATH" ni belgilang.
        pause
        exit /b 1
    )
    python -m venv .venv
    call .venv\Scripts\activate.bat
    echo [*] Kutubxonalar o'rnatilmoqda...
    pip install -r requirements.txt >nul 2>&1
) else (
    call .venv\Scripts\activate.bat
)

:: 2. Papkalarni hozirlash
if not exist "data" mkdir data
if not exist "data\snapshots" mkdir data\snapshots

echo.
echo ======================================================
echo    🟢 Chaqimchi AI muvaffaqiyatli ishga tushdi!
echo    Boshqaruv paneli: http://localhost:8750
echo ======================================================
echo.

:: Brauzerda avtomatik ochish (Onboarding Usta)
start http://localhost:8750/onboarding


:: Asosiy serverni ishga tushirish
python -m cloud.main
pause
