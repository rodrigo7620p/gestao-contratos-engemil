@echo off
setlocal
cd /d "%~dp0"
title Gestao Contratual ENGEMIL

if exist "%~dp0configuracao_email.bat" call "%~dp0configuracao_email.bat"

if not exist "%~dp0.venv\Scripts\python.exe" (
    echo Preparando o ambiente Python na primeira execucao...
    where py >nul 2>&1
    if not errorlevel 1 (
        py -3 -m venv "%~dp0.venv"
    ) else (
        where python >nul 2>&1
        if errorlevel 1 (
            echo Python nao foi localizado. Instale o Python 3.11 ou superior.
            pause
            exit /b 1
        )
        python -m venv "%~dp0.venv"
    )
)

"%~dp0.venv\Scripts\python.exe" -c "import streamlit,reportlab,extra_streamlit_components,requests,PIL" >nul 2>&1
if errorlevel 1 (
    if exist "%~dp0vendor\extra_streamlit_components-0.1.81-py3-none-any.whl" (
        "%~dp0.venv\Scripts\python.exe" -m pip install "%~dp0vendor\extra_streamlit_components-0.1.81-py3-none-any.whl"
    )
    "%~dp0.venv\Scripts\python.exe" -m pip install -r "%~dp0requirements.txt"
    if errorlevel 1 (
        echo Nao foi possivel instalar as dependencias.
        echo Verifique a internet e execute novamente este arquivo.
        pause
        exit /b 1
    )
)

"%~dp0.venv\Scripts\python.exe" -c "from db import init_db; init_db()"
if errorlevel 1 (
    echo Nao foi possivel atualizar a estrutura do banco.
    pause
    exit /b 1
)

echo Sistema disponivel nesta maquina em http://localhost:8501
echo Para acesso na rede interna, use http://IP-DESTA-MAQUINA:8501
"%~dp0.venv\Scripts\python.exe" -m streamlit run "%~dp0app.py"
endlocal
