@echo off
cd /d "%~dp0"
if exist "%~dp0configuracao_turso.bat" call "%~dp0configuracao_turso.bat"
call .venv\Scripts\activate.bat
.venv\Scripts\python.exe backup_diario.py
