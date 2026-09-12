# Gestão de Contratos ENGEMIL — instruções do projeto

Streamlit + Turso (libSQL), publicado em
`https://gestao-contratos-engemil.streamlit.app/`. `app.py` é o script
principal (~12k linhas); `contract_tasks.py`, `alerts.py`, `bids.py`,
`guarantees.py`, `db.py` etc. concentram a lógica de cada área.

## Ao entregar qualquer atualização visível ao usuário

1. Bump de `APP_VERSION` em `app.py` + nova entrada em `VERSAO.txt`
   (changelog técnico, versão a versão — padrão já estabelecido nas
   entradas anteriores do arquivo).
2. **Atualize `MANUAL_DO_SISTEMA.md`** — a seção do módulo afetado, o mapa
   do menu (seção 2) se uma página mudou, e a seção 6 se um comportamento
   de e-mail/automação mudou. Esse arquivo descreve o **estado atual**, sem
   histórico (histórico é o `VERSAO.txt`) — é o manual de uso e mapa da
   plataforma para futuros usuários e administradores, e a instrução
   explícita é mantê-lo sempre em dia, na mesma tarefa da mudança, nunca
   como pendência à parte.
3. Republique a versão em HTML do manual como Artifact, usando o mesmo
   `url` já publicado:
   `https://claude.ai/code/artifact/799b5250-ffd6-4e82-b449-137de7c7cffd`
   — use `action: "read"` com essa URL para conferir o conteúdo publicado
   antes de reenviar, e publique passando esse mesmo `url` para atualizar
   em vez de criar uma nova página. Se a URL acima não abrir mais (o
   artefato foi movido/recriado), use `action: "list"` para localizar o
   atual antes de publicar, e atualize esta linha com a URL correta.
4. Rode a suíte de regressão (`.venv\Scripts\python.exe test_core.py`)
   sempre com `GESTAO_SMTP_CONFIG` apontando para um caminho inexistente
   (ou com `notifications.send_email` substituído por um stub) — nunca
   deixe um teste disparar e-mail real.
5. Testes de e-mail que precisem enviar de verdade vão SEMPRE para
   `rodrigo.silva@engemil.com.br`, nunca para listas de distribuição reais
   (ex.: `gestao.contratos@engemileng.com`).
6. Commit + push para `origin main`; confirme o deploy lendo o título da
   aba de login em `https://gestao-contratos-engemil.streamlit.app/` (deve
   mostrar a nova versão) via Browser tool.

## Documentação do projeto

- `MANUAL_DO_SISTEMA.md` — manual de uso e mapa da plataforma (estado
  atual, sem histórico). Fonte de verdade para usuários/administradores.
- `VERSAO.txt` — changelog técnico, uma entrada por versão.
- `README.md`, `GESTAO_LICITACOES.md`, `GESTAO_SESMT.md` — documentos mais
  antigos, com boa parte do conteúdo já superada pelo `MANUAL_DO_SISTEMA.md`
  (o README em especial está desatualizado, ainda descrevendo a v27 só com
  instalação local). Ainda não foram retirados de circulação; ao tocar em
  algo que eles descrevem, prefira corrigir o manual novo, e considere
  sinalizar ao usuário que esses arquivos antigos merecem uma limpeza.
