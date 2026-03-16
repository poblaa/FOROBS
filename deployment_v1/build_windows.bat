@echo off
setlocal

echo ======================================
echo FOROBS v3 - Windows build
echo ======================================

echo.
if not exist venv\Scripts\activate (
  echo ERROR: Missing venv. Run install_from_cache_windows.bat first.
  pause
  exit /b 1
)

call venv\Scripts\activate
if errorlevel 1 (
  echo ERROR: Could not activate venv.
  pause
  exit /b 1
)

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist FOROBS.spec del /q FOROBS.spec

pyinstaller --onefile --name FOROBS ^
  --add-data "app.py;." ^
  --add-data "transfer_agent.py;." ^
  --add-data "auto_transfer.py;." ^
  --add-data "card_settings.json;." ^
  --add-data "card_layout.json;." ^
  --add-data "elcalc;elcalc" ^
  --hidden-import streamlit ^
  --hidden-import pandas ^
  --hidden-import openpyxl ^
  --hidden-import altair ^
  --hidden-import plotly ^
  --collect-all streamlit ^
  forobs_launcher.py

if errorlevel 1 (
  echo.
  echo ERROR: Build failed.
  pause
  exit /b 1
)

echo.
echo Build finished. Output should be in dist\FOROBS.exe
pause
