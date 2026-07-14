@echo off
setlocal
cd /d "%~dp0"
title Finalizar Timer Task Master
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0finalizar_timertaskmaster.ps1"
echo.
pause
