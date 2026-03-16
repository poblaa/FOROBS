@echo off
setlocal

echo ======================================
echo FOROBS v3 - install from local cache
echo ======================================

echo.
echo This script expects Python 3.12 for Windows to be already installed.
echo.

if not exist download_cache_windows (
  echo ERROR: Folder download_cache_windows not found.
  pause
  exit /b 1
)

py -3.12 -m venv venv
if errorlevel 1 (
  echo ERROR: Could not create venv with py -3.12
  pause
  exit /b 1
)

call venv\Scripts\activate
if errorlevel 1 (
  echo ERROR: Could not activate venv.
  pause
  exit /b 1
)

python -m pip install --no-index --find-links=download_cache_windows streamlit pandas openpyxl altair pyinstaller plotly
if errorlevel 1 (
  echo ERROR: Offline package install failed.
  pause
  exit /b 1
)

echo.
echo DONE: local environment prepared from cache.
pause
