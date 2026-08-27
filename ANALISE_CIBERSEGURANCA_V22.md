# Análise de cibersegurança — Gestão Contratual ENGEMIL V22

Data da revisão: 31/07/2026

## Resultado executivo

A versão 22 recebeu controles adequados para os testes locais e para uma futura
publicação controlada. Isso não equivale a uma certificação ou teste de invasão.
Antes de liberar acesso externo, os itens críticos deste documento devem ser
concluídos e validados no servidor definitivo.

## Controles implementados na V22

- autorização por módulo e por ação: consultar, lançar, modificar e excluir;
- ambiente **Usuários** oculto e bloqueado no servidor para não administradores;
- proteção contra exclusão/desativação do último administrador;
- desativação e exclusão de contas, desbloqueio, redefinição de 2FA e
  revogação de todas as sessões;
- senha inicial temporária com troca obrigatória no primeiro acesso;
- frase-senha com no mínimo 15 caracteres, rejeição de valores previsíveis e de
  trechos do nome/e-mail;
- bloqueio da conta por 15 minutos após cinco tentativas inválidas;
- hash PBKDF2-SHA256 com salt individual para senhas;
- token de sessão aleatório, armazenado apenas como hash, revogável e com
  expiração por 30 minutos de inatividade;
- cookie `SameSite=Strict` e `Secure` quando a conexão é HTTPS;
- proteções CORS e XSRF habilitadas e serviço limitado a `127.0.0.1`;
- bloqueio de anexos executáveis e neutralização de caminhos/nomes de arquivo;
- trilha de auditoria para login recusado, alteração de permissões, sessões,
  2FA, criação, modificação e exclusão;
- consultas de banco parametrizadas nas operações de autenticação e gestão
  de usuários.

## Riscos e ações obrigatórias antes de colocar online

| Prioridade | Risco | Ação exigida |
|---|---|---|
| Crítica | Windows 10 sem suporte regular | Migrar o computador-servidor para Windows 11/Windows Server suportado ou contratar ESU antes de expor o serviço. |
| Crítica | Tráfego sem criptografia | Publicar somente por proxy reverso com HTTPS, certificado válido e redirecionamento de HTTP para HTTPS. Nunca encaminhar a porta 8501 no roteador. |
| Crítica | Roubo do computador ou do disco | Ativar BitLocker, senha forte no Windows, bloqueio automático de tela e conta de serviço sem privilégios administrativos. |
| Alta | Comprometimento de senha | Tornar 2FA obrigatório para administradores e para qualquer perfil que lança, modifica ou exclui dados. |
| Alta | Perda/corrupção do banco e anexos | Backup automático criptografado de `gestao_contratos.db`, `uploads` e `trash`, com cópia desconectada e teste mensal de restauração. |
| Alta | Vazamento da senha SMTP | Manter `configuracao_email.bat` fora dos pacotes, restringir ACL ao usuário do serviço e usar senha de aplicativo exclusiva e rotacionável. |
| Alta | Arquivo malicioso permitido dentro de ZIP/Office | Ativar Microsoft Defender em tempo real e varredura agendada da pasta `uploads`; considerar quarentena antes de disponibilizar downloads. |
| Alta | Administração remota do computador | Não expor RDP. Usar VPN com MFA e permitir acesso administrativo somente de dispositivos autorizados. |
| Média | Alteração local da auditoria SQLite | Exportar periodicamente os logs para armazenamento somente de acréscimo ou para outro equipamento. |
| Média | Dependências desatualizadas | Revisar mensalmente Python, Streamlit e bibliotecas; testar a atualização em cópia antes de aplicar na produção. |
| Média | Indisponibilidade elétrica/rede | Usar nobreak, reinício automático do serviço e monitoramento de disponibilidade/espaço em disco. |

## Arquitetura recomendada para publicação

1. Navegador acessa exclusivamente `https://contratos.engemil.com.br`.
2. O roteador/firewall entrega apenas a porta 443 ao proxy reverso.
3. O proxy aplica o certificado TLS e encaminha internamente para
   `127.0.0.1:8501`.
4. O Streamlit não aceita conexões diretas da internet.
5. Banco, anexos e segredos permanecem no disco criptografado do servidor.
6. Backup criptografado é enviado para destino separado e testado regularmente.

## Conferência operacional mensal

- revisar administradores, contas inativas e permissões de exclusão;
- revisar tentativas de login recusadas e redefinições de 2FA;
- confirmar que o backup foi concluído e restaurar uma cópia de teste;
- aplicar atualizações do sistema operacional e do antivírus;
- verificar validade do certificado HTTPS e espaço livre em disco;
- revogar imediatamente contas de pessoas desligadas ou que mudaram de função;
- executar os testes `test_core.py` a `test_v22.py` após qualquer atualização.

## Referências técnicas

- Microsoft — Windows 10 support has ended:
  https://support.microsoft.com/en-us/windows/deployment/updates-lifecycle/windows-10-support-has-ended-on-october-14-2025
- Streamlit — configuração de CORS, XSRF e servidor:
  https://docs.streamlit.io/develop/api-reference/configuration/config.toml
- OWASP — Authorization Cheat Sheet:
  https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- OWASP — Session Management Cheat Sheet:
  https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- OWASP — Secrets Management Cheat Sheet:
  https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
- NIST SP 800-63B — autenticação, senhas e sessões:
  https://pages.nist.gov/800-63-4/sp800-63b.html
