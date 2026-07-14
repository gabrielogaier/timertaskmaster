@echo off
setlocal
cd /d "%~dp0"
title Timer Task Master - DEBUG

call :find_python
if errorlevel 1 exit /b 1

if not exist ".venv\Scripts\python.exe" (
    echo Criando ambiente virtual...
    "%PYTHON_CMD%" -m venv .venv
    if errorlevel 1 goto :error
)

set "VENV_PYTHON=%CD%\.venv\Scripts\python.exe"
"%VENV_PYTHON%" -c "import PySide6, openpyxl" >nul 2>&1
if errorlevel 1 (
    echo Instalando dependencias...
    "%VENV_PYTHON%" -m pip install --upgrade pip
    if errorlevel 1 goto :error
    "%VENV_PYTHON%" -m pip install -r requirements.txt
    if errorlevel 1 goto :error
)

echo.
echo Iniciando Timer Task Master em modo debug...
echo.
"%VENV_PYTHON%" "%CD%\app.py"
set "EXIT_CODE=%ERRORLEVEL%"
echo.
echo Timer Task Master encerrado. Codigo de saida: %EXIT_CODE%
pause
exit /b %EXIT_CODE%

:find_python
where py >nul 2>&1
if not errorlevel 1 (set "PYTHON_CMD=py" & exit /b 0)
where python >nul 2>&1
if not errorlevel 1 (set "PYTHON_CMD=python" & exit /b 0)
echo Python 3 nao foi encontrado.
echo Instale o Python 3 e marque Add Python to PATH.
pause
exit /b 1

:error
echo Ocorreu uma falha durante a preparacao do projeto.
pause
exit /b 1
