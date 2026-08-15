@echo off
chcp 65001 > nul
title Chaqimchi AI - Windows O'rnatuvchi

echo ======================================================
echo    Chaqimchi AI - Do'kon Analitikasi (Windows)
echo ======================================================
echo.

:: 1. Python mavjudligini tekshirish
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [XATO] Kompyuteringizda Python o'rnatilmagan!
    echo Iltimos, Python 3.11 yoki 3.12 ni https://www.python.org dan yuklab o'rnating.
    echo "Add python.exe to PATH" katagiga belgi qo'yishni unutmang.
    pause
    exit /b 1
)

echo [1/4] Python aniqlandi. Virtual muhit (venv) yaratilmoqda...
if not exist ".venv" (
    python -m venv .venv
)

echo [2/4] Kerakli kutubxonalar o'rnatilmoqda...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt

echo [3/4] Ma'lumotlar papkalari tayyorlanmoqda...
if not exist "data" mkdir data
if not exist "data\snapshots" mkdir data\snapshots
if not exist "data\clips" mkdir data\clips
if not exist "data\backup" mkdir data\backup

echo [4/4] Tizim tekshiruvdan o'tkazilmoqda...
python -c "import cv2; import fastapi; print('[OK] Barcha asosiy modullar muvaffaqiyatli yuklandi!')"

echo.
echo ======================================================
echo    O'rnatish muvaffaqiyatli yakunlandi!
echo    Tizimni ishga tushirish uchun "run_windows.bat" ni bosing.
echo ======================================================
echo.
pause
