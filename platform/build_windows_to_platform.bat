@echo off
setlocal

echo ======================================
echo FOROBS Platform - build Windows release
echo ======================================

set SRC=..\deployment_v1.2
set OUT=windows_release\FOROBS

if not exist "%SRC%\build_windows.bat" (
  echo ERROR: Missing %SRC%\build_windows.bat
  pause
  exit /b 1
)

if exist "%OUT%" rmdir /s /q "%OUT%"
mkdir "%OUT%" >nul 2>&1

echo.
echo Step 1/2: running deployment_v1.2\build_windows.bat
pushd "%SRC%"
call build_windows.bat
set BUILD_EXIT=%ERRORLEVEL%
popd

if not "%BUILD_EXIT%"=="0" (
  echo.
  echo ERROR: build_windows.bat failed with code %BUILD_EXIT%.
  pause
  exit /b %BUILD_EXIT%
)

if not exist "%SRC%\dist\FOROBS\FOROBS.exe" (
  echo.
  echo ERROR: Expected file not found: %SRC%\dist\FOROBS\FOROBS.exe
  pause
  exit /b 1
)

echo.
echo Step 2/2: copying build to platform output
xcopy /E /I /Y "%SRC%\dist\FOROBS" "%OUT%\" >nul

echo.
echo ======================================
echo Build ready:
echo   platform\%OUT%\FOROBS.exe
echo ======================================
pause
exit /b 0
