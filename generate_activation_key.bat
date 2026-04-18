@echo off
setlocal EnableExtensions

cd /d "%~dp0"

set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    set "PYTHON_EXE=python"
)

set "INTERACTIVE=0"
set "MACHINE_ID=%~1"
if "%MACHINE_ID%"=="" (
    set "INTERACTIVE=1"
    echo.
    set /p MACHINE_ID=Enter Machine ID ^(example: TC-XXXXXXXXXXXX^): 
)

if "%MACHINE_ID%"=="" (
    echo.
    echo No Machine ID entered.
    if "%INTERACTIVE%"=="1" pause
    exit /b 1
)

echo.
echo Generating activation key for: %MACHINE_ID%
echo.

"%PYTHON_EXE%" "%~dp0generate_activation_key.py" --machine-id "%MACHINE_ID%"
if errorlevel 1 (
    echo.
    echo Activation key generation failed.
    echo Make sure Python or .venv is available in this folder.
    if "%INTERACTIVE%"=="1" pause
    exit /b 1
)

echo.
echo Copy the key shown above and send it to the client.
echo.
if "%INTERACTIVE%"=="1" pause
exit /b 0
