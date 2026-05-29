@echo off
chcp 65001 >nul
echo ==============================
echo   WS-OSC Build Script
echo ==============================

echo.
echo [1/3] Installing dependencies...
pip install -r requirements.txt

echo.
echo [2/3] Building exe with PyInstaller...
python -m PyInstaller --noconfirm --onefile --windowed ^
    --name "WS_OSC_Server" ^
    --add-data "requirements.txt;." ^
    --hidden-import pystray._win32 ^
    --hidden-import PIL ^
    --hidden-import PIL._tkinter_finder ^
    websocket_to_osc.py

echo.
echo [3/3] Build complete!
echo.
echo Output: dist\WS_OSC_Server.exe
echo.
pause
