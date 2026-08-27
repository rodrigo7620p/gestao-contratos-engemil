@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" verificar_integridade.py
) else (
    python verificar_integridade.py
)
echo.
pause
endlocal
