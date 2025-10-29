@echo off
REM Deepr installation script for Windows

echo Installing Deepr...
echo.

REM Check Python version
python --version
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.9 or higher from python.org
    pause
    exit /b 1
)

echo.
echo Installing Deepr package...
pip install -e .

if errorlevel 1 (
    echo.
    echo ERROR: Installation failed
    pause
    exit /b 1
)

echo.
echo Installation complete!
echo.
echo Next steps:
echo   1. Copy .env.example to .env
echo   2. Edit .env and add your OPENAI_API_KEY
echo   3. Run: deepr --version
echo.
pause
