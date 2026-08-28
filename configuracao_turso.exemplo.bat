@echo off
rem Copie este arquivo para configuracao_turso.bat e preencha localmente.
rem Necessario para que tarefas agendadas rodando neste computador (como o
rem envio diario de licitacoes) leiam o MESMO banco usado pelo app publicado
rem na nuvem, em vez do arquivo gestao_contratos.db local.
rem Nunca encaminhe, sincronize publicamente ou inclua o token em pacotes
rem de atualizacao.
set "TURSO_DATABASE_URL=libsql://SEU-BANCO-SUAORG.turso.io"
set "TURSO_AUTH_TOKEN=SEU_TOKEN_AQUI"
