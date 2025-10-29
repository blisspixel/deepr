@echo off
REM Deepr build script for Windows

echo Building Deepr...

REM Clean previous builds
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist deepr.egg-info rmdir /s /q deepr.egg-info

REM Build distribution
python -m build

echo.
echo Build complete! Distribution packages are in dist/
echo.
echo To install: pip install dist\deepr-2.3.0-py3-none-any.whl
