@echo off
cd /d "%~dp0"

echo Installing build dependencies...
pip install pyinstaller pywin32 pystray Pillow

echo.
echo Building LogOverlay.exe...
pyinstaller --onefile --noconsole --name=LogOverlay --add-data="config.ini;." --hidden-import=pystray._win32 log_overlay.py

echo.
echo Copying config.ini to dist folder...
copy config.ini dist\config.ini

echo.
echo ============================================
echo  Build complete!
echo  Files ready in dist\ folder:
echo    - LogOverlay.exe
echo    - config.ini
echo ============================================
echo.
pause
