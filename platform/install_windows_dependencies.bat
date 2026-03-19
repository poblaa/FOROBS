@echo off
setlocal

echo ======================================
echo FOROBS Platform - install dependencies
echo ======================================

if not exist "..\deployment_v1.2\install_windows.bat" (
  echo ERROR: Missing ..\deployment_v1.2\install_windows.bat
  pause
  exit /b 1
)

pushd "..\deployment_v1.2"
call install_windows.bat
set EXITCODE=%ERRORLEVEL%
popd

if not "%EXITCODE%"=="0" (
  echo.
  echo ERROR: install_windows.bat failed with code %EXITCODE%.
  pause
  exit /b %EXITCODE%
)

echo.
echo Dependencies installed.
pause
exit /b 0
