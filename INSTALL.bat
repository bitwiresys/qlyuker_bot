@echo off

cd /d "%~dp0"

:: Check if the "sessions" folder exists
if not exist "sessions" (
    echo The "sessions" folder was not found. Creating...
    mkdir "sessions"
) else (
    echo The "sessions" folder already exists.
)
cls

:: Check if the ".conf" file exists
if not exist ".conf" (
    echo The ".conf" file was not found. Creating...
    echo # Configuration file > "config.conf"
) else (
    echo The ".conf" file already exists.
)

python -m venv venv

call venv\Scripts\activate

cls

python.exe -m pip install --upgrade pip

pip install -r requirements.txt

cls

:: Adding a choice between registration and running the main script
echo Please choose an action:
echo 1. Registration
echo 2. Launch
set /p choice="Enter the action number (1 or 2): "

if "%choice%"=="1" (
    cls
    python reg.py
    echo Registration completed.
) else if "%choice%"=="2" (
    cls
    python main.py
    python main_script.py  :: Replace with the name of your main script
) else (
    echo Invalid choice. Please run the script again.
)

pause