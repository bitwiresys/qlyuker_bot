@echo off
cd /d "%~dp0"
call venv\Scripts\activate

:MENU
cls
echo Choose an action:
echo 1. Registration
echo 2. Launch
echo 3. Exit
set /p choice=Enter the number (1-3): 

if "%choice%"=="1" (
	cls
    python reg.py
    pause
    goto MENU
) else if "%choice%"=="2" (
	cls
    python main.py
    pause
    goto MENU
) else if "%choice%"=="3" (
    exit
) else (
    echo Invalid input. Please try again.
    pause
    goto MENU
)