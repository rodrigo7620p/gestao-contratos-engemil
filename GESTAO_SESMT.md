# Módulo SESMT — GESTÃO_CONTRATOS_ENGEMIL (a partir da V31)

## O que o módulo faz

Cria um espaço dedicado para o SESMT (Serviço Especializado em Engenharia
de Segurança e em Medicina do Trabalho) acompanhar, por profissional e
associado ao contrato em que ele está alocado:

- **Exames ocupacionais (ASO)**: admissional, periódico, demissional,
  mudança de função, retorno ao trabalho — com data, resultado (apto/apto
  com restrição/inapto) e validade.
- **Treinamentos e certificados** (NRs, brigada de incêndio etc.): nome,
  instituição/instrutor, carga horária, data de emissão e validade.
- **Documentos anexados** por exame ou por treinamento (o próprio ASO ou
  certificado em PDF/imagem), reaproveitando o mesmo mecanismo de upload
  já usado no restante do sistema (bloqueio de extensões perigosas,
  limite de tamanho, exclusão controlada por permissão).

A tela inicial mostra indicadores (profissionais ativos, exames vencidos,
exames vencendo em 30 dias, treinamentos vencidos/vencendo), filtros por
status/contrato/nome, e uma lista com a data do próximo vencimento de
exame e de treinamento de cada profissional — para que o SESMT identifique
rapidamente quem precisa ser reagendado, sem abrir ficha por ficha.

## Por que todo profissional precisa de um contrato vinculado

O cadastro de profissional exige selecionar um contrato. Isso não é uma
limitação técnica arbitrária — foi uma escolha deliberada para atender ao
pedido de "associar a contrato", e também porque a tabela de documentos do
sistema (já usada por todos os outros módulos) exige um contrato de
referência para organizar os arquivos em disco. Se a ENGEMIL tiver
profissionais do quadro próprio sem vínculo com um contrato específico
(ex.: equipe interna do SESMT), sugiro cadastrar um "contrato" interno
simbólico (ex.: centro de custo "ADMINISTRATIVO") só para servir de guarda-
chuva a esses casos — ou pedir que eu adapte o modelo para tornar o vínculo
opcional, o que exigiria uma migração maior na tabela de documentos.

## Novo perfil de usuário: SESMT

Foi criado o perfil `sesmt`, selecionável na tela Usuários e permissões,
com as mesmas regras de segurança dos demais perfis (senha, 2FA opcional,
bloqueio por tentativas). Por padrão, um usuário com perfil SESMT:

- **Vê todos os módulos** (como qualquer perfil, por padrão — pode ser
  restringido manualmente na tela de permissões, por usuário);
- **Só tem permissão de lançar e editar dados no módulo SESMT** por
  padrão — diferente de "operador"/"gestor"/"engenheiro", que já vêm com
  permissão de lançamento em todos os módulos. Isso segue o princípio de
  menor privilégio: a diretoria pediu um perfil para o SESMT fazer os
  lançamentos *dele*, não acesso geral de edição ao restante do sistema.
- Se precisar que um usuário SESMT também edite contratos, ARTs ou outro
  módulo, ajuste manualmente em Usuários → permissões daquele usuário,
  exatamente como já é feito para os demais perfis.

## Estrutura de dados

- `sesmt_professionals`: um registro por profissional acompanhado,
  sempre vinculado a um contrato (`contract_id`, `ON DELETE CASCADE` —
  mesmo comportamento já usado para ARTs).
- `sesmt_exams`: um registro por exame ocupacional, vinculado ao
  profissional.
- `sesmt_trainings`: um registro por treinamento/certificado, vinculado
  ao profissional.
- `documents` ganhou três colunas novas (`sesmt_professional_id`,
  `sesmt_exam_id`, `sesmt_training_id`) para reaproveitar o mecanismo de
  upload já existente, sem duplicar lógica de arquivo.

## Alertas automáticos por e-mail (a partir da V33)

Exames ocupacionais (ASO) e treinamentos/certificados com validade cadastrada
agora entram automaticamente no mesmo mecanismo de alertas usado para
obrigações contratuais e garantias (`alerts.py` → `process_sesmt_alerts`),
disparado por `executar_alertas.bat` (manual ou pelo Agendador de Tarefas,
via `configurar_alertas_automaticos.bat`).

- Janelas de aviso: 30 dias antes, 15 dias antes, e no dia do vencimento
  (ou já vencido).
- Como o cadastro do profissional não tem um e-mail de contato próprio, o
  aviso vai para o **engenheiro responsável** do contrato ao qual o
  profissional está vinculado — e, na falta dele, para o **responsável
  administrativo** do mesmo contrato. Mesmo padrão de fallback já usado
  nos alertas de garantias.
- Cada combinação (evento + destinatário + data) só é enviada uma vez —
  reaproveita a tabela `notification_log` já existente, sem risco de
  reenviar o mesmo aviso repetidamente.
- Se nenhum e-mail estiver disponível (nem engenheiro, nem responsável
  administrativo cadastrado no contrato), o registro aparece na lista
  `sesmt_missing_email` do resultado do processamento, para você
  identificar contratos sem e-mail de contato.

## Possíveis próximos passos (não implementados ainda)

- **Exportação em Excel/PDF** da relação de profissionais com pendências,
  no mesmo padrão dos relatórios já existentes — rápido de adicionar
  depois, se for útil no dia a dia do SESMT.
- Um **e-mail de contato específico por profissional ou por SESMT** (hoje
  os alertas vão para o engenheiro/responsável do contrato) — se a
  diretoria preferir que o SESMT receba diretamente, é uma mudança
  pequena.
