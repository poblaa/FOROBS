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

rem -----------------------------------------------------------------------
rem --onedir: creates dist\FOROBS\ folder with FOROBS.exe inside.
rem App files (app.py, jsons, elcalc) are NOT bundled – they are copied
rem next to the exe after the build so they are easy to update/replace.
rem
rem WHY NOT --onefile?
rem   With --onefile sys.executable IS the generated exe.
rem   subprocess.run(sys.executable, "-m", "streamlit", ...) would call the
rem   exe again → infinite loop → 10 browser tabs.
rem   We use stcli.main() in the launcher so subprocess is not needed at all.
rem -----------------------------------------------------------------------

pyinstaller --onedir --name FOROBS ^
  --hidden-import streamlit ^
  --hidden-import pandas ^
  --hidden-import openpyxl ^
  --hidden-import altair ^
  --hidden-import plotly ^
  --hidden-import transfer_agent ^
  --hidden-import auto_transfer ^
  --collect-all streamlit ^
  forobs_launcher.py

if errorlevel 1 (
  echo.
  echo ERROR: PyInstaller build failed.
  pause
  exit /b 1
)

rem --- Copy app files next to the exe so they are found via cwd ----------
echo.
echo Copying app files to dist\FOROBS\ ...
copy /Y app.py                dist\FOROBS\
copy /Y transfer_agent.py     dist\FOROBS\
copy /Y auto_transfer.py      dist\FOROBS\
copy /Y card_settings.json    dist\FOROBS\
copy /Y card_layout.json      dist\FOROBS\
if exist elcalc (
  xcopy /E /I /Y elcalc       dist\FOROBS\elcalc\
)

echo.
echo ======================================
echo Build finished!
echo Distribute the entire dist\FOROBS\ folder.
echo Users double-click FOROBS.exe to launch.
echo ======================================
pause
