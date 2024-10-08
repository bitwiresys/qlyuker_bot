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

pause