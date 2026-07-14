@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Criar executavel - Timer Task Master

set "APP_EXE=dist\Timer Task Master.exe"
set "NO_PAUSE=0"
set "BUILD_ICON=.build-assets\timertaskmaster.ico"
if /I "%~1"=="--no-pause" set "NO_PAUSE=1"

call :find_python
if errorlevel 1 goto :error

if not exist ".venv-build\Scripts\python.exe" (
    echo Criando ambiente de compilacao...
    "%PYTHON_CMD%" -m venv .venv-build
    if errorlevel 1 goto :error
)
set "BUILD_PYTHON=%CD%\.venv-build\Scripts\python.exe"

"%BUILD_PYTHON%" -c "import PyInstaller, PySide6, openpyxl" >nul 2>&1
if errorlevel 1 (
    echo Instalando ferramentas de compilacao...
    "%BUILD_PYTHON%" -m pip install --upgrade pip
    if errorlevel 1 goto :error
    "%BUILD_PYTHON%" -m pip install -r requirements.txt -r requirements-build.txt
    if errorlevel 1 goto :error
)

if exist build rmdir /s /q build
if exist "%APP_EXE%" del /q "%APP_EXE%"
if exist "Timer Task Master.spec" del /q "Timer Task Master.spec"
if not exist ".build-assets" mkdir ".build-assets"
if exist "%BUILD_ICON%" del /q "%BUILD_ICON%"

set "SOURCE_ICON="
for /f "delims=" %%I in ('dir /b /a-d /on "icons\*.ico" 2^>nul') do (
    if not defined SOURCE_ICON set "SOURCE_ICON=icons\%%I"
)
if not defined SOURCE_ICON (
    echo ERRO: nenhum arquivo .ico foi encontrado em icons.
    goto :error
)
copy /y "%SOURCE_ICON%" "%BUILD_ICON%" >nul
if errorlevel 1 goto :error

echo Criando executavel...
"%BUILD_PYTHON%" -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --windowed ^
    --name "Timer Task Master" ^
    --icon "%BUILD_ICON%" ^
    --add-data "icons;icons" ^
    --version-file "installer\version_info.txt" ^
    "app.py"
if errorlevel 1 goto :error
if not exist "%APP_EXE%" goto :error

echo.
echo Executavel criado: %CD%\%APP_EXE%
if "%NO_PAUSE%"=="0" (start "" "%CD%\dist" & pause)
exit /b 0

:find_python
where py >nul 2>&1
if not errorlevel 1 (set "PYTHON_CMD=py" & exit /b 0)
where python >nul 2>&1
if not errorlevel 1 (set "PYTHON_CMD=python" & exit /b 0)
echo Python 3 nao foi encontrado.
exit /b 1

:error
echo.
echo Nao foi possivel criar o executavel.
if "%NO_PAUSE%"=="0" pause
exit /b 1
