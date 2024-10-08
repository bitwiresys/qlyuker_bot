@echo off
REM Ожидание завершения основного Python-скрипта
timeout /t 2 /nobreak >nul

REM Скачивание репозитория с GitHub
echo Скачивание обновления...
curl -L -o update.zip https://github.com/yourusername/yourrepo/archive/refs/heads/main.zip

REM Распаковка архива
echo Распаковка архива...
powershell -Command "Expand-Archive -Path 'update.zip' -DestinationPath '.' -Force"

REM Переход в распакованную папку
set "EXTRACTED_DIR=yourrepo-main"

REM Копирование файлов, кроме .conf
echo Копирование файлов...
for /r "%EXTRACTED_DIR%" %%F in (*) do (
    if /i not "%%~nxF"==".conf" (
        xcopy /Y /I "%%F" "%~dp0%%~nxF"
    )
)

REM Удаление временных файлов
echo Очистка временных файлов...
rmdir /S /Q "%EXTRACTED_DIR%"
del update.zip

REM Обновление локальной версии
echo Обновление версии...
curl -L -o .ver https://raw.githubusercontent.com/yourusername/yourrepo/main/version.txt

REM Запуск основного скрипта после обновления (если необходимо)
REM echo Запуск основного скрипта...
REM python main_script.py

echo Обновление завершено.