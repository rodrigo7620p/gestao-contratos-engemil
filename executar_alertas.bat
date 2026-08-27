@echo off
cd /d "%~dp0"
if exist "%~dp0configuracao_email.bat" call "%~dp0configuracao_email.bat"
call .venv\Scripts\activate.bat
.venv\Scripts\python.exe alerts.py
