@echo off
cd /d "%~dp0"
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
set "TAREFA=ENGEMIL - Backup Diario"
set "COMANDO=%~dp0executar_backup_diario.bat"
schtasks /Create /TN "%TAREFA%" /TR "\"%COMANDO%\"" /SC DAILY /ST 08:00 /F
if errorlevel 1 (
    echo Nao foi possivel criar a tarefa. Execute este arquivo como Administrador.
    pause
    exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$task=Get-ScheduledTask -TaskName '%TAREFA%'; $task.Settings.StartWhenAvailable=$true; Set-ScheduledTask -InputObject $task | Out-Null" >nul 2>&1
echo.
echo Tarefa "%TAREFA%" configurada para executar todo dia as 08:00.
echo Se o computador estiver desligado nesse horario, a tarefa iniciara quando possivel.
echo O backup fica salvo em Backups\AAAA-MM-DD dentro desta mesma pasta do sistema
echo (que ja sincroniza com o OneDrive, entao ganha uma copia na nuvem de brinde) —
echo banco de dados completo (todas as tabelas) e todos os documentos anexados,
echo prontos para rodar o sistema localmente se precisar. Backups com mais de 30
echo dias sao apagados automaticamente a cada execucao, para nao crescer sem limite.
echo Para testar agora, execute executar_backup_diario.bat diretamente.
pause
