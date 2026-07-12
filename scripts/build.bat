@echo off
REM Deepr build script for Windows

echo Building Deepr...

REM Clean previous builds
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist deepr.egg-info rmdir /s /q deepr.egg-info

REM Build the dashboard that ships inside the Python package
pushd src\deepr\web\frontend
call npm ci
if errorlevel 1 exit /b 1
call npm run build
if errorlevel 1 exit /b 1
popd
python scripts\build_frontend_archive.py
if errorlevel 1 exit /b 1

REM Build distribution
python -m build
if errorlevel 1 exit /b 1

for %%W in (dist\*.whl) do python scripts\check_wheel_frontend.py "%%W"
if errorlevel 1 exit /b 1

echo.
echo Build complete! Distribution packages are in dist/
echo.
echo To install: pip install dist\*.whl
