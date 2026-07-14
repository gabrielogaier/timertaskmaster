@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Criar instalador - Timer Task Master

echo Etapa 1 de 2: criando o executavel...
call build_executavel.bat --no-pause
if errorlevel 1 goto :error

echo.
echo Etapa 2 de 2: preparando o instalador...
set "ISCC="
for %%P in (
    "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
    "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
    "%ProgramFiles%\Inno Setup 6\ISCC.exe"
) do if exist "%%~P" set "ISCC=%%~P"

if not defined ISCC (
    where winget >nul 2>&1
    if errorlevel 1 (
        echo Inno Setup 6 nao encontrado e winget indisponivel.
        goto :error
    )
    echo Instalando Inno Setup 6...
    winget install --id JRSoftware.InnoSetup --exact --accept-package-agreements --accept-source-agreements
    if errorlevel 1 goto :error
    for %%P in (
        "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
        "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
        "%ProgramFiles%\Inno Setup 6\ISCC.exe"
    ) do if exist "%%~P" set "ISCC=%%~P"
)

if not defined ISCC goto :error
"%ISCC%" "installer\setup.iss"
if errorlevel 1 goto :error

echo.
echo Instalador criado: %CD%\dist\installer\TimerTaskMaster-Setup.exe
start "" "%CD%\dist\installer"
pause
exit /b 0

:error
echo.
echo Nao foi possivel criar o instalador.
pause
exit /b 1
