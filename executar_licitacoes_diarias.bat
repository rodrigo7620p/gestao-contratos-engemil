@echo off
cd /d "%~dp0"
if exist "%~dp0configuracao_email.bat" call "%~dp0configuracao_email.bat"
if exist "%~dp0configuracao_turso.bat" call "%~dp0configuracao_turso.bat"
call .venv\Scripts\activate.bat
.venv\Scripts\python.exe alerts.py --bid-schedule
