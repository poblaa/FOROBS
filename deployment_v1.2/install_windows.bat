@echo off
setlocal
echo ======================================
echo FOROBS v3 - Windows install (online)
echo ======================================
echo.
echo Requires: Python 3.12 x64  (python.org/downloads)
echo Internet connection needed for first install.
echo.

python --version >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python not found. Install Python 3.12 x64 and make sure it is
  echo        added to PATH, then re-run this script.
  pause
  exit /b 1
)

echo Creating virtual environment...
python -m venv venv
if errorlevel 1 (
  echo ERROR: Could not create venv.
  pause
  exit /b 1
)

echo Installing packages...
call venv\Scripts\activate
pip install --upgrade pip
pip install streamlit==1.41.0 pandas openpyxl altair plotly pyinstaller

if errorlevel 1 (
  echo ERROR: pip install failed.
  pause
  exit /b 1
)

echo.
echo ======================================
echo Install finished.
echo Next step: run  build_windows.bat
echo ======================================
pause
