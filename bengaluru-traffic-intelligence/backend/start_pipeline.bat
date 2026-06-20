@echo off
REM BTP Intelligence — Full Pipeline Runner (Windows)
REM Run this from the backend\ directory after placing incidents.csv in data\raw\

set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo.
echo ============================================================
echo  BTP Intelligence Pipeline
echo  Expected runtime: 8-15 minutes on 3 lakh row dataset
echo ============================================================
echo.

REM Pre-flight check
python verify_setup.py
if errorlevel 1 (
    echo.
    echo  Pre-flight check failed. Fix the issues above.
    pause
    exit /b 1
)

echo.
echo  Starting pipeline...
echo.

python pipeline\run_all.py

if errorlevel 1 (
    echo.
    echo  Pipeline failed. Check errors above.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Pipeline complete! Now run: start_api.bat
echo ============================================================
pause
