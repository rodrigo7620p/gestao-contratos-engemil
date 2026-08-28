@echo off
cd /d "%~dp0"
if not exist "%~dp0configuracao_email.bat" (
    echo Configure primeiro o arquivo configuracao_email.bat.
    echo Use configuracao_email.exemplo.bat como modelo.
    pause
    exit /b 1
)
if not exist "%~dp0configuracao_turso.bat" (
    echo Configure primeiro o arquivo configuracao_turso.bat.
    echo Use configuracao_turso.exemplo.bat como modelo ^(precisa apontar
    echo para o MESMO banco usado pelo app publicado na nuvem^).
    pause
    exit /b 1
)
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo O ambiente Python ainda nao foi instalado. Execute instalar.bat primeiro.
    pause
    exit /b 1
)
icacls "%~dp0configuracao_turso.bat" /inheritance:r /grant:r "%USERNAME%:F" "SYSTEM:F" >nul 2>&1
set "TAREFA=ENGEMIL - Licitacoes do Dia"
set "COMANDO=%~dp0executar_licitacoes_diarias.bat"
schtasks /Create /TN "%TAREFA%" /TR "\"%COMANDO%\"" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 06:50 /F
if errorlevel 1 (
    echo Nao foi possivel criar a tarefa. Execute este arquivo como Administrador.
    pause
    exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$task=Get-ScheduledTask -TaskName '%TAREFA%'; $task.Settings.StartWhenAvailable=$true; Set-ScheduledTask -InputObject $task | Out-Null" >nul 2>&1
echo.
echo Tarefa "%TAREFA%" configurada para executar de segunda a sexta as 06:50.
echo Se o computador estiver desligado nesse horario, a tarefa iniciara quando possivel.
echo (o proprio sistema tambem tenta enviar sozinho, como reforco, se alguem
echo abrir o app depois das 06:50 num dia util e o envio ainda nao tiver saido)
echo Para testar agora, execute executar_licitacoes_diarias.bat diretamente.
pause
