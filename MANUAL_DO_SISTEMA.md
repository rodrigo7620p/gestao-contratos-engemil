# Manual do Sistema — Gestão de Contratos ENGEMIL

> **Versão do sistema documentada aqui: 101 Beta.**
> Este manual é mantido junto do código: sempre que uma atualização muda,
> adiciona ou remove uma funcionalidade, este arquivo (e a página publicada
> equivalente) é revisado na mesma tarefa, como parte do próprio trabalho —
> nunca como uma pendência à parte. Veja a seção 8 para os detalhes desse
> compromisso.

Este documento é o mapa e o manual de uso completo da plataforma **Gestão
de Contratos ENGEMIL** — um sistema web interno para centralizar contratos,
aditivos, garantias, ARTs, licitações, SESMT, documentos padronizados e
todas as comunicações automáticas por e-mail relacionadas a essas rotinas.
Ele foi escrito para dois públicos:

- **Usuários do dia a dia** (engenheiros, gestores, administrativo, SESMT):
  seção 5, organizada exatamente como o menu do sistema.
- **Futuros controladores/administradores do sistema** (quem for dar
  manutenção, treinar novos usuários ou tomar decisões técnicas): seções
  3, 6, 7 e 8, com o funcionamento interno, hospedagem e como manter este
  próprio manual em dia.

## Sumário

1. [Visão geral da plataforma](#1-visão-geral-da-plataforma)
2. [Mapa do menu](#2-mapa-do-menu)
3. [Perfis de usuário e permissões](#3-perfis-de-usuário-e-permissões)
4. [Primeiro acesso, login e segurança](#4-primeiro-acesso-login-e-segurança)
5. [Instruções de uso por módulo](#5-instruções-de-uso-por-módulo)
   - [5.1 Visão geral](#51-visão-geral)
   - [5.2 Contratos (Backlog)](#52-contratos-backlog)
   - [5.3 Ficha do Contrato](#53-ficha-do-contrato)
   - [5.4 Novo contrato](#54-novo-contrato)
   - [5.5 Pré-contratos](#55-pré-contratos)
   - [5.6 Licitações](#56-licitações)
   - [5.7 SESMT](#57-sesmt)
   - [5.8 Exportações](#58-exportações)
   - [5.9 Índices](#59-índices)
   - [5.10 Documentos padrões](#510-documentos-padrões)
   - [5.11 Usuários (administração)](#511-usuários-administração)
   - [5.12 Manual do sistema](#512-manual-do-sistema)
6. [Comunicações automáticas por e-mail](#6-comunicações-automáticas-por-e-mail)
7. [Administração técnica e hospedagem](#7-administração-técnica-e-hospedagem)
8. [Como este manual é mantido atualizado](#8-como-este-manual-é-mantido-atualizado)

---

## 1. Visão geral da plataforma

O sistema é um painel web (acessado pelo navegador, sem instalar nada na
máquina do usuário) que substitui o controle de contratos antes feito em
planilha. Ele guarda, para cada contrato da ENGEMIL:

- Dados cadastrais, vigência, valores originais e vigentes;
- Aditivos, apostilamentos e demais instrumentos contratuais;
- Garantias contratuais e seguros (com apólices, coberturas e endossos);
- ARTs e CNOs;
- BDI e regime de faturamento;
- Sindicatos, datas-base, cargos, benefícios e a equipe nominal alocada;
- Prazos e obrigações administrativas, com cobrança automática por e-mail;
- Documentos anexados a cada um desses registros.

Além da carteira de contratos já firmados, o sistema também controla a
**carteira de licitações** em andamento (antes de virarem contrato) e o
**SESMT** (exames ocupacionais e treinamentos da equipe). Um módulo de
**Documentos padrões** gera Ofícios, Procurações e Cartas de Preposto em
Word a partir de modelos da empresa.

Todo o sistema também **avisa sozinho, por e-mail**, quando algo precisa de
atenção: um contrato vencendo, uma garantia sem apólice registrada, uma
obrigação atrasada, uma providência (garantia/ART) pedida e ainda não
lançada no sistema. A seção 6 detalha cada um desses avisos.

## 2. Mapa do menu

O menu lateral ("Navegação") lista as páginas que o usuário logado tem
permissão de ver. Da esquerda/topo para baixo:

| Página | Para que serve |
|---|---|
| **Visão geral** | Painel inicial: indicadores da carteira, gráficos, avisos de dados pendentes e de garantias a conferir. |
| **Contratos** | Backlog consolidado de toda a carteira, com filtros, projeção de remanescente e exportação em Excel/PDF. |
| **Ficha do contrato** | Abre o cadastro completo de um contrato específico — o coração do sistema (aditivos, garantias, BDI, sindicatos, equipe, obrigações, ARTs, CNO e edição geral). |
| **Novo contrato** | Cadastra um contrato novo, formalizado ou como pré-contrato (centro de custo reservado, sem número de contrato ainda). |
| **Pré-contratos** | Acompanha os centros de custo reservados que ainda não têm número de contrato, e prepara o e-mail de anúncio. |
| **Licitações** | Carteira de licitações em disputa, separada dos contratos já firmados — classificação, PNCP, exportações. |
| **SESMT** | Profissionais, exames ocupacionais (ASO) e treinamentos/NRs da equipe. |
| **Exportações** | Central de downloads (Excel/PDF) de qualquer parte do sistema. |
| **Índices** | Cálculo dos índices financeiros e declaração oficial em PDF. |
| **Documentos padrões** | Geração de Ofício, Carta de Preposto e Procuração a partir de modelos Word da empresa. |
| **Usuários** | Exclusivo do administrador — cadastro de contas, permissões e auditoria. |
| **Manual do sistema** | Este manual, direto dentro da plataforma — sempre o último item do menu. |

Cada usuário só vê as páginas para as quais tem permissão de visualização
(ver seção 3) — exceto **Manual do sistema**, sempre visível a qualquer
perfil, por não entrar no sistema de permissões por módulo. O tema
(Escuro/Claro) e o último menu aberto ficam salvos por usuário e são
restaurados automaticamente, inclusive depois de um F5.

## 3. Perfis de usuário e permissões

Cada conta tem um **perfil** e, dentro de cada módulo, quatro permissões
independentes: **Visualizar**, **Lançar novos itens**, **Modificar
existentes** e **Excluir itens**.

| Perfil | O que já vem liberado por padrão |
|---|---|
| **Administrador** | Acesso total a tudo, incluindo a página Usuários, exclusão definitiva de registros e o histórico completo de auditoria. |
| **Gestor** | Visualiza tudo; lança e edita em todos os módulos por padrão (exclusão não vem liberada — precisa ser ajustada manualmente). |
| **Engenheiro** | Mesmo padrão do Gestor: visualiza tudo, lança e edita em todos os módulos. |
| **Operador** | Visualiza tudo e lança novos itens em qualquer módulo, mas não edita nem exclui por padrão. |
| **SESMT** | Visualiza tudo, mas só lança/edita dados **dentro do módulo SESMT** — os demais módulos ficam em modo consulta, a menos que seja ampliado manualmente. |
| **Consulta (viewer)** | Só visualiza. Nenhuma permissão de lançamento, edição ou exclusão em nenhum módulo, por padrão. |

Qualquer uma dessas permissões pode ser ajustada individualmente, por
usuário e por módulo, na página **Usuários** (seção 5.11) — os valores da
tabela acima são só o ponto de partida ao criar a conta. Marcar Lançar,
Modificar ou Excluir sempre liga Visualizar automaticamente junto.

Duas exclusividades que não passam por essa tabela:
- Só o **administrador** pode enviar um e-mail de teste de SMTP (dentro da
  Ficha do Contrato, aba "Prazos e obrigações").
- Só o **administrador** acessa a página **Usuários**.

## 4. Primeiro acesso, login e segurança

- **Login**: e-mail e senha, na tela inicial.
- **Credenciais do primeiro acesso** (antes de qualquer usuário próprio ser
  criado): `admin@engemil.local` / `Alterar@123`.
- **Troca de senha obrigatória**: toda conta nova (ou que teve a senha
  redefinida pelo administrador) é forçada a criar uma senha pessoal antes
  de ver qualquer outra tela. A senha temporária não pode ser reaproveitada.
- **Política de senha**: mínimo de 8 caracteres, com maiúscula, minúscula e
  caractere especial; não pode conter o nome nem o e-mail do usuário.
- **Verificação em duas etapas (2FA)**: desligada por padrão; o
  administrador decide, por usuário, se vai ser exigida. Quando exigida e
  ainda não configurada, o sistema bloqueia todo o resto até o usuário
  vincular um aplicativo Authenticator (Google Authenticator, Microsoft
  Authenticator ou equivalente) pelo QR Code mostrado na tela. Mantenha
  data/hora automáticas no celular e no servidor — os códigos dependem
  disso (o sistema aceita até 60 segundos de diferença).
- **Sessão persistente**: atualizar a página com F5 não desloga o usuário.
- **Encerramento por inatividade**: 30 minutos sem nenhuma interação
  encerram a sessão automaticamente (ajustável pelo administrador via
  variável de ambiente, ver seção 7). Trocar a senha encerra todas as
  outras sessões abertas daquela conta.
- **Alterar minha senha** e **Segurança e 2FA**: expansores sempre
  disponíveis na barra lateral, para qualquer usuário logado.
- **Sair**: botão na barra lateral; a próxima entrada começa em "Visão
  geral".

## 5. Instruções de uso por módulo

### 5.1 Visão geral

Painel inicial, calculado só sobre contratos **ativos, formalizados e com
vigência ainda válida**.

- Indicadores: contratos vigentes, valor atual da carteira, remanescente
  total, e quantos contratos vencem nos próximos 90 dias (em destaque
  quando houver algum).
- Gráfico de valor vigente pelos 10 maiores centros de custo.
- Gráfico de valor vencendo por mês, nos próximos 12 meses.
- **Painel de conferência cadastral**: aponta contratos vigentes com
  campos pendentes (ex.: responsável administrativo, prazo final ou valor
  atual não preenchidos) — expanda para ver o motivo de cada pendência e
  use o botão **Abrir ficha para corrigir**.
- **Garantias e seguros da carteira**: indicadores de vigência (60 dias),
  documentação recebida e pendências de conferência, com lista das
  garantias pendentes e atalho direto para a ficha de cada uma.
- Gráficos de valor e quantidade por modalidade (Manutenção, Obra,
  Reforma, ATA, Consórcio, Outro).
- Remanescente previsto ano a ano (6 anos) e ranking dos 5 contratos com
  maior valor remanescente disponível.

### 5.2 Contratos (Backlog)

Lista consolidada de toda a carteira.

- **Responsáveis por providências iniciais**: cadastro de quem recebe o
  e-mail de pendências (ativação no TOTVS, garantia contratual, ART)
  sempre que um contrato novo é lançado ou um aditivo/apostilamento é
  anexado — permite mais de um e-mail por responsável, pausar/reativar e
  um grupo de e-mails compartilhado que sempre recebe o aviso junto.
- Filtro Ativos/Arquivados/Todos e pesquisa livre por órgão, número,
  processo, objeto ou centro de custo.
- Projeção de remanescente ano a ano (6 anos) a partir do ano escolhido,
  com prazo restante e situação de cada contrato.
- Tabela consolidada com todas as colunas do backlog e os totais do filtro
  atual.
- Exportação em Excel e em PDF (uma página, com dashboard da carteira na
  segunda página).

### 5.3 Ficha do Contrato

A tela mais completa do sistema — abre o cadastro inteiro de um contrato
específico, organizado em abas. Ao abrir, mostra sempre os cartões de
resumo (contrato, processo, valores original/vigente, instrumento vigente,
prazo restante, regime de faturamento) e depois as abas abaixo. As abas
**Sindicatos e datas-base**, **Equipe e cargos**, **Prazos e obrigações**,
**ARTs**, **CNO** e **Editar** aparecem sempre; **Contratos decorrentes da
ATA** só aparece quando o contrato é do tipo ATA.

#### Resumo

- Objeto do contrato, dados rápidos (engenheiro, responsável
  administrativo, tamanho da equipe, sindicatos vinculados, próxima
  repactuação, datas do orçamento) e observações gerais.
- **Preparar ficha completa em Word**: gera um dossiê Word com todas as
  abas preenchidas (omite o que estiver vazio), pronto para download.
- **Documentos gerais do contrato**: anexos que não pertencem a nenhum
  aditivo/garantia/ART/CNO específico.

#### Aditivos

- Tabela de todos os instrumentos contratuais (contrato inicial +
  aditivos/apostilamentos/termos), com valor, datas, duração em meses
  (calculada sozinha) e as colunas automáticas "Garantias vinculadas" e
  "ARTs vinculadas".
- **Adicionar aditivo**: número/ordem, tipo (Termo Aditivo, Termo de
  Apostilamento, Contrato, ou "Outro" com nome livre), valor atualizado,
  datas, descrição e observações.
- Cada instrumento tem seus próprios documentos. O botão **Reenviar aviso
  de providências** reenvia o e-mail de garantia/ART usando o último
  documento já anexado, sem precisar reanexar nada — útil quando o e-mail
  original não chegou (ex.: falha temporária de SMTP).
- **Anexar ao instrumento**: upload do documento do aditivo/apostilamento.
  A caixa **"Instrumento apenas informativo"** evita disparar o aviso de
  garantia/ART quando o documento não altera valor nem prazo (ex.:
  correção de dados, apostilamento formal).
- **Excluir instrumento contratual**: bloqueado se houver garantia
  vinculada a ele.

> **Como funciona o aviso de providências (garantia contratual e ART)** —
> ver seção 6.1 para o fluxo completo dos dois e-mails (o de "instrumento
> assinado" e o pedido exclusivo de garantia) e da cobrança automática de
> 30 dias.

#### Garantias e seguros

- Indicadores: total de garantias/seguros, documentos pendentes,
  vencimentos em 60 dias e pontos para conferência (apólice, vigência ou
  documentação com problema) — expanda **Exibir pontos para conferência**
  para ver o detalhe de cada um.
- Tabela com tipo, instrumento, modalidade, situação, apólice, base de
  cálculo, valor exigido e vigência de cada registro.
- **Solicitar/Reenviar garantia contratual ao responsável**: formulário
  completo (prazo do órgão — sugerido automaticamente 30 dias após a
  homologação —, percentual exigido com cálculo automático do valor,
  referência da base — total/anual/manual —, modalidade, anexos do
  certame). Ao enviar, dispara o e-mail exclusivo de garantia para o(s)
  responsável(is) cadastrado(s) e grava o pedido como "SOLICITADA". Esta
  seção só aparece enquanto a garantia principal do contrato ainda não
  estiver com o processo concluído.
- **Cadastrar garantia ou seguro**: formulário completo, pré-preenchido
  com o valor do contrato e o responsável.
- Cada garantia/seguro cadastrado abre em 4 sub-abas: **Dados e edição**,
  **Coberturas e franquias** (LMI, vigência, franquia/POS), **Endossos e
  renovações** (histórico de movimentações, sem sobrescrever a apólice
  original) e **Documentos** (vinculados à apólice principal ou a um
  endosso específico).
- **Excluir garantia/seguro**: bloqueado se houver documentos vinculados.

#### BDI

- **Regime de faturamento**: Não definido / Onerado / Desonerado, com
  alerta enquanto não for definido.
- Cada contrato pode ter várias composições de BDI (ex.: "BDI 1 — Mão de
  obra", "BDI 2 — Materiais"), cada uma calculada por **Soma direta**
  (custos indiretos + lucro + tributos) ou **Fórmula composta**
  (Administração Central, Seguros, Riscos, Garantias, outros custos
  indiretos, Despesas Financeiras, Lucro e Tributos, com PIS/COFINS/ISS/
  CPRB detalhados separadamente).
- Alertas de inconsistência (ex.: regime onerado com CPRB zerado).
- Cadastrar, editar e excluir composições de BDI.

#### Contratos decorrentes da ATA (só quando o contrato é uma ATA)

- Tabela de todos os contratos já formalizados a partir da ATA.
- Editar dados, cadastrar novo contrato decorrente (com upload opcional do
  documento assinado — dispara o aviso de providências iniciais) e excluir
  (bloqueado se houver garantia vinculada).
- Cada contrato decorrente tem sua própria aba de **Aditivos** (mesma
  lógica da aba principal, incluindo o aviso "apenas informativo") e seus
  próprios **documentos**.

#### Sindicatos e datas-base

- Tabela de sindicatos/CCT vinculados: sindicato, CCT, categoria, mês e
  data-base, próxima repactuação, instrumento contratual de referência.
- Adicionar, editar e remover vínculos; documentos por sindicato/CCT.

#### Equipe e cargos

- **Tabela de cargos** (planejamento por quantidade): cargo, quantidade,
  salário-base, periculosidade e insalubridade (%), com cálculo automático
  de periculosidade em R$, base e valor da insalubridade, benefícios,
  custo por empregado e custo mensal da equipe inteira.
- **Benefícios por cargo**: plano de saúde, odontológico, seguro de vida,
  vale-alimentação/refeição, auxílio-creche ou outro, com valor mensal por
  empregado.
- **Atualizar salário mínimo anual**: parâmetro usado como base de cálculo
  da insalubridade quando o cargo não tem ano-base próprio.
- **Funcionários nominais**: diferente da tabela de cargos (que é só
  planejamento por quantidade), esta guarda o nome de cada pessoa
  realmente alocada no contrato — nome, cargo, CPF, admissão, salário-base,
  status. Pode ser cadastrada manualmente ou **importada de uma planilha do
  RH** (o sistema tenta reconhecer as colunas automaticamente, mas sempre
  pede confirmação do mapeamento antes de gravar; se a planilha tiver
  coluna de centro de custo, só importa as linhas deste contrato). Esses
  nomes ficam disponíveis para reaproveitar ao cadastrar um profissional no
  módulo **SESMT**, sem redigitar.

#### Prazos e obrigações

- Indicadores de obrigações pendentes, prazos vencidos e alertas ativos.
- Aviso se o e-mail do engenheiro responsável não estiver preenchido (isso
  impede os avisos de encerramento de vigência de saírem).
- **Histórico dos alertas de encerramento** já enviados (30/15 dias).
- **Configuração e teste dos alertas por e-mail**: mostra a configuração
  SMTP efetiva (sem revelar a senha) e permite enviar um e-mail de teste
  (só administrador).
- **Registrar obrigação**: título, categoria, vencimento, prioridade,
  responsável e e-mail, recorrência, antecedência do primeiro alerta,
  frequência das cobranças, orientações — com opção de já disparar o
  primeiro e-mail ao salvar.
- **Enviar cobrança agora**: reenvio manual e imediato de uma obrigação
  pendente específica.

#### ARTs

- Tabela organizada por profissional, com instrumento contratual vinculado
  (contrato inicial, aditivo, ATA ou contrato/aditivo decorrente).
- **Cadastrar ART**: reaproveita nome/título/registro de um profissional já
  usado em qualquer contrato, ou permite um novo; valida número de ART
  duplicado dentro do contrato.
- Editar (inclusive trocar o instrumento vinculado — atualiza a coluna
  "ARTs vinculadas" da aba Aditivos automaticamente), anexar documento e
  excluir.

#### CNO

- Radio **"Este contrato exige inscrição no CNO?"** (A definir/Sim/Não) —
  o cadastro só é liberado quando marcado "Sim". Em contratos ATA, cada CNO
  precisa ser associado a um contrato decorrente específico.
- Cadastrar CNO (número de inscrição, data de cadastramento, início da
  responsabilidade, área de atuação), anexar documentos e excluir.

#### Editar

- Formulário com todos os campos cadastrais do contrato: centro de custo,
  número, modalidade, órgão/objeto, edital/processo/UASG, data de
  homologação, datas de vigência (atual e originais), valores, quantidade
  de meses de referência do valor, status, regime de faturamento,
  engenheiro/responsável administrativo, próxima repactuação e
  observações.
- **Datas do orçamento**: várias referências (data, descrição,
  observações) por contrato.
- **Arquivar contrato finalizado** / **Restaurar contrato para a carteira
  ativa**.
- **Zona de exclusão**: exige digitar o centro de custo exato para
  habilitar a exclusão definitiva (os documentos vão para uma pasta de
  lixeira administrativa, não são apagados na hora).

### 5.4 Novo contrato

Cadastro de contratos novos — formalizados de imediato ou como
pré-contrato (sem número ainda).

- **Origem do contrato**: opção para indicar se o contrato é oriundo de
  uma licitação já cadastrada no menu Licitações. Ao escolher uma
  licitação (só aparecem as ainda não vinculadas a nenhum contrato), os
  campos abaixo são preenchidos automaticamente com os dados já lançados
  nela — órgão, objeto, edital, número do processo, UASG, modalidade da
  licitação, modalidade/escopo do contrato, valor (nosso lance vencedor) e
  o responsável pelo acompanhamento — revisáveis antes de salvar. Ao
  cadastrar, a licitação escolhida fica vinculada ao contrato criado.
  Contratações diretas (sem licitação, ou com uma licitação ainda não
  cadastrada no sistema) usam a opção padrão "Nenhuma" e seguem exatamente
  como antes.
- **Centro de custo**: gerado e sequenciado automaticamente a partir da
  modalidade escolhida (padrão `01.YY.ZZZZZ`), ou digitado manualmente.
- Engenheiro/responsável administrativo: reaproveita alguém já cadastrado
  em outro contrato ou cadastra uma pessoa nova.
- Modalidade da licitação (lista da Lei 14.133/2021, com opção livre).
- Campos completos do contrato: número (deixe em branco para virar
  pré-contrato), órgão, objeto, edital/processo/UASG, data de homologação,
  datas de vigência, valor original, meses de referência do valor, regime
  de faturamento, próxima repactuação, observações.
- **Garantia (opcional)**: percentual, garantia adicional (Lei 14.133/2021,
  art. 59, §5º) e referência do valor-base (total ou anual estimado).
- **BDI (opcional)** e **anexos do certame** (Edital, Termo de Referência,
  Planilha, Proposta homologada, Minuta do contrato).
- **Sindicatos e datas-base** e **Equipe e cargos** iniciais, já na mesma
  tela.
- Upload opcional do contrato assinado.
- Ao salvar: dispara o aviso de providências iniciais (garantia
  contratual, ART, ativação no TOTVS) para os responsáveis cadastrados,
  com o documento anexado quando disponível.

### 5.5 Pré-contratos

Acompanha os centros de custo reservados (sem número de contrato ainda).

- **E-mails de anúncio**: lista de destinatários fixos reutilizada em todo
  envio do e-mail de anúncio de pré-contrato.
- Um cartão por pré-contrato pendente, com atalho **Abrir ficha** e a
  situação atual da garantia contratual.
- **Preparar e-mail de anúncio**: assunto e corpo totalmente editáveis,
  com prévia de como sai a tabela de garantia/BDI (calculada a partir dos
  dados já cadastrados na ficha), seleção de anexos do certame e envio
  para os destinatários fixos + engenheiro/responsável administrativo.

### 5.6 Licitações

Carteira de licitações em disputa, separada dos contratos já firmados.
Cada licitação tem número de processo, UASG, edital, plataforma, órgão,
UF, objeto, modalidade, valor estimado, status, data/hora da disputa,
nosso lance final, desconto e classificação — podendo ser vinculada a um
contrato quando é homologada e assinada.

- **Notificação diária de licitações do dia**: todo dia útil às 6h50, um
  quadro com as disputas marcadas para aquele dia (dia, hora, UASG,
  número, órgão, escopo, objeto e valor estimado) sai automaticamente para
  uma lista de e-mails cadastrável.
- Indicadores (em andamento, taxa de sucesso, valor estimado/em disputa) e
  filtros por status, plataforma, escopo, texto e período da disputa. O
  filtro de status é de múltipla escolha e já vem com **"Em andamento"**
  marcado por padrão — acrescente outros status (ex.: Suspensa) para ver
  mais de um ao mesmo tempo, ou remova a seleção para ver a carteira
  inteira.
- **Cadastro**: escolha da estrutura do certame (item único / vários itens
  individuais / grupo(s) com itens, com detalhamento item a item e gerador
  automático de linhas), com responsável pré-preenchido.
- **Aba Classificação**: cole a tabela de empresas direto do portal (o
  sistema reconhece dois formatos diferentes automaticamente), edite
  manualmente linha a linha (com CNPJ e situação — Classificada/
  Desclassificada/Inabilitada/Desistente) e gere a **imagem PNG** de
  classificação no padrão visual da ENGEMIL, com a linha da ENGEMIL
  destacada e a data/hora da disputa identificada — pronta para encaminhar
  aos gestores.
- **Consultar contratações publicadas no PNCP**: busca pública por
  período, modalidade, UF e CNPJ do órgão; o botão "Verificar no PNCP" (na
  aba Resumo e edição de cada licitação) confirma automaticamente quando o
  órgão já homologou um contrato com a ENGEMIL.
- **Documentos do PNCP**: a partir do número de controle PNCP, baixa
  automaticamente o edital e seus anexos, compactados num único arquivo.
- **Exportar em PDF**: relatório de uma página A4 horizontal, com as
  colunas escolhidas e respeitando os filtros aplicados na tela.
- **Excluir licitação**: remove o processo, seus grupos/itens e toda a
  classificação.

### 5.7 SESMT

Cadastro de profissionais vinculados a um contrato, com exames
ocupacionais e treinamentos/certificados.

- Indicadores: profissionais ativos, exames vencidos/vencendo em 30 dias,
  treinamentos vencidos/vencendo.
- **Cadastrar profissional**: sempre vinculado a um contrato; pode
  reaproveitar nome/cargo de um funcionário já cadastrado na aba "Equipe e
  cargos" daquele contrato.
- Ficha do profissional em 3 abas: **Dados e edição**, **Exames
  ocupacionais (ASO)** (tipo, data, resultado, validade, documento
  anexado) e **Treinamentos e certificados** (NRs e outros, com sugestões
  pré-cadastradas como NR-06/10/11/12/18/33/35 e Brigada de Incêndio).
- Alertas automáticos de vencimento (30/15 dias e vencido) vão para o
  engenheiro responsável do contrato (ou o responsável administrativo, na
  falta dele) — o cadastro do profissional não tem e-mail próprio.

### 5.8 Exportações

Central de downloads, sempre gerados na hora a partir do banco de dados:

- Visão Geral, Contratos/Backlog (Excel e PDF), Índices e histórico de
  Documentos padrões, cada um em Excel separado.
- **Ficha individual**: Excel completo de um contrato específico
  escolhido, junto com seus documentos.
- **Arquivo consolidado**: um único Excel com todas as abas.
- **Importação legada de planilha** (só administrador/gestor): atualiza
  contratos a partir de uma planilha de "análise crítica" pelo centro de
  custo, sem alterar o arquivo original enviado.

### 5.9 Índices

Cálculo dos índices financeiros (considerando só contratos ativos,
formalizados e vigentes) e emissão da declaração oficial.

- Indicadores: valor total, remanescente, "PL × 12 / Contratos" e
  "PL × 12 / Remanescente" (meta mínima 1,00).
- Parâmetros contábeis: ano de referência, patrimônio líquido, receita
  bruta, justificativa (com texto padrão sugerido) e dados de quem assina.
- **Gerar declaração oficial em PDF**: duas páginas A4 vertical (relação de
  contratos + fórmulas/justificativa/assinatura) — exige um responsável
  pela assinatura definido antes de gerar.

### 5.10 Documentos padrões

Geração de Ofício, Carta de Preposto e Procuração a partir de modelos Word
da empresa.

- **Gerar documento**: escolhe o modelo, vincula opcionalmente a um
  contrato (pré-preenche campos), escolhe o responsável pela assinatura; o
  formulário se adapta sozinho aos marcadores do modelo escolhido. Numera
  o documento automaticamente e salva o histórico.
- **Histórico e encaminhamento**: todos os documentos já gerados, com
  status (Gerado/Em revisão/Aprovado/Encaminhado/Cancelado), data de
  encaminhamento e observações/protocolo.
- **Modelos e assinaturas** (administrador): cadastro de novos modelos
  Word (aceita `.docx`/`.dotm`/`.dotx`, com os marcadores `{{ORGAO}}`,
  `{{CONTRATO}}`, `{{ASSUNTO}}`, `{{CORPO_TEXTO}}`, `{{RESPONSAVEL}}`,
  `{{DADOS}}`, `{{CARGO}}`) e gestão dos responsáveis pelas assinaturas.

### 5.11 Usuários (administração)

Exclusivo do administrador.

- Tabela de todos os usuários (perfil, ativo, 2FA, troca de senha
  pendente, bloqueado, último acesso).
- **Criar usuário**: nome, e-mail, senha inicial, perfil (Consulta,
  Lançamento, SESMT, Engenheiro, Gestor, Administrador), exigir 2FA — a
  conta já nasce com troca de senha obrigatória no primeiro acesso.
- **Segurança e ciclo de vida da conta**: mudar perfil, ativar/desativar,
  exigir 2FA, desbloquear tentativas, redefinir 2FA e encerrar todas as
  sessões abertas de um usuário.
- **Permissões por ambiente**: tabela por módulo com Visualizar/Lançar/
  Modificar/Excluir, ajustável usuário a usuário (não é possível alterar
  permissões de outro administrador).
- **Excluir usuário**: exige digitar o e-mail exato; nunca remove o último
  administrador ativo; preserva auditoria e documentos já gerados por essa
  conta.
- **Atividades recentes**: últimas 100 ações registradas em todo o
  sistema.

### 5.12 Manual do sistema

Este próprio manual, sempre o último item do menu, disponível a qualquer
perfil. Mostra o conteúdo direto do arquivo `MANUAL_DO_SISTEMA.md`
versionado no repositório e traz um link para a página publicada, mais
confortável para leitura e navegação pelo sumário.

## 6. Comunicações automáticas por e-mail

Todo aviso automático depende do SMTP estar configurado (arquivo
`configuracao_email.bat` local, ou os `SMTP_*` equivalentes na nuvem — ver
seção 7). Sem isso, o sistema continua funcionando normalmente, só não
envia e-mail — cada tela avisa quando um envio falhou e por quê.

### 6.1 Providências de garantia contratual e ART

Sempre que um contrato é formalizado, um aditivo/apostilamento é anexado,
ou um contrato/aditivo decorrente de ATA é lançado, o sistema confere se
já existe garantia contratual e ART vinculadas àquele instrumento
específico:

1. **E-mail "ASSINADO"**: para o grupo de e-mails cadastrado + o
   engenheiro/responsável administrativo, listando as providências ainda
   pendentes (ativação no TOTVS, ART) com o documento assinado em anexo.
   Quando a garantia contratual ainda está pendente, este e-mail traz só
   uma linha informativa avisando que uma solicitação exclusiva foi
   enviada à parte (ou o motivo de ainda não ter sido, ver item 3).
2. **E-mail "SOLICITACAO-GARANTIA"**, enviado alguns segundos depois (para
   preservar a ordem no histórico das caixas de entrada): exclusivo para
   os responsáveis cadastrados pela garantia contratual + o engenheiro —
   **sem** o e-mail de grupo. Leva em anexo o instrumento atual e, quando
   existir, o último documento de garantia já registrado no sistema (do
   contrato inicial ou do aditivo anterior), para a corretora ter a
   referência de continuidade da apólice.
3. **Trava de continuidade**: a solicitação de garantia só sai se o
   instrumento **anterior** do mesmo contrato já tiver a garantia dele
   registrada no sistema com um documento anexado. Faltando isso, o
   sistema não envia e explica, no e-mail "ASSINADO" e na tela, que é
   preciso completar o cadastro do instrumento anterior primeiro.
4. **Reconhecimento do que já foi pedido**: se a garantia já tiver sido
   solicitada antes (inclusive em um pré-contrato, antes da assinatura),
   o sistema não pede de novo — a aba Garantias e seguros também tem seu
   próprio botão **Solicitar/Reenviar garantia** (seção 5.3) para os casos
   em que o órgão pede a indicação da modalidade com antecedência.

**Cobrança automática de cadastro**: se passarem 30 dias corridos desde a
solicitação (de garantia ou de ART) sem que o registro correspondente seja
lançado no sistema, um e-mail de cobrança sai automaticamente para os
mesmos destinatários do pedido original — e se repete a cada 30 dias
enquanto continuar pendente, parando sozinho assim que o cadastro é feito.
Reenvios (o botão "Reenviar aviso de providências") não reiniciam essa
contagem — só a primeira solicitação conta para o prazo.

### 6.2 Prazos, obrigações e vigências

- **Obrigações administrativas** (aba Prazos e obrigações): cobrança
  conforme a antecedência e a frequência configuradas em cada uma,
  continuando enquanto o status não for Concluída/Cancelada.
- **Repactuação de CCT**: ao informar a próxima repactuação de um
  sindicato, o sistema cria automaticamente uma obrigação com 90 dias de
  antecedência.
- **Encerramento de vigência**: aviso ao engenheiro responsável quando
  faltarem até 30 dias e, de novo, até 15 dias para o fim da vigência
  atual. Cada aviso (contrato + data final + destinatário) só sai uma vez;
  um novo aditivo que mude a vigência reinicia esse ciclo para a nova data.
- **Garantias e seguros**: vencimento de vigência em 60/30/15 dias e prazo
  para apresentação do documento, quando configurado.
- **SESMT**: exames ocupacionais e treinamentos vencendo em 30/15 dias ou
  já vencidos.
- **Licitações do dia**: quadro diário (dias úteis, 6h50) com as disputas
  marcadas para aquele dia.

## 7. Administração técnica e hospedagem

Esta seção é para quem for dar manutenção técnica ao sistema.

### Hospedagem e banco de dados

- O sistema roda publicado no **Streamlit Community Cloud**
  (`gestao-contratos-engemil.streamlit.app`), a partir do repositório
  Git. O disco desse serviço é **efêmero** — é apagado a cada reinício —
  então os dados de verdade nunca ficam só nele.
- **Banco de dados**: [Turso](https://turso.tech/) (SQLite hospedado,
  acessado via `libsql-client`). As credenciais (`TURSO_DATABASE_URL`,
  `TURSO_AUTH_TOKEN`) ficam nos "Secrets" do Streamlit Cloud; localmente,
  em `configuracao_turso.bat` (nunca versionado no Git). Sem essas
  variáveis configuradas, o sistema volta a usar um arquivo SQLite local —
  é o que acontece automaticamente em desenvolvimento.
- **Documentos anexados**: também sobrevivem ao disco efêmero — a pasta
  `uploads/` é compactada e sincronizada dentro do próprio banco (tabela
  `blob_store`) sempre que muda, e restaurada automaticamente quando o
  sistema reinicia.
- **Backup diário completo**: `backup_diario.py` copia todas as tabelas do
  Turso e todos os documentos para uma pasta local `Backups/AAAA-MM-DD/`
  — um `.db` autônomo (funciona offline, sem depender do Turso) mais a
  pasta `uploads/` de verdade. Backups com mais de 30 dias são apagados
  automaticamente.

### Automações agendadas (GitHub Actions)

Rodam na nuvem do GitHub, sem depender de nenhum computador ligado
(`.github/workflows/`):

- **`licitacoes-diarias.yml`**: dispara `python alerts.py --bid-schedule`
  todo dia útil às 6h50 (horário de Brasília) — envia o quadro de
  licitações do dia.
- **`manter-app-acordado.yml`**: faz um `ping` ao app publicado a cada 10
  minutos, só para evitar a hibernação do Streamlit Community Cloud.

Os demais alertas periódicos (`alerts.process_repactuation_alerts`, que
processa obrigações, repactuações, vencimento de contratos, garantias e
SESMT) rodam automaticamente no **primeiro acesso de cada sessão**, uma
vez por login — não têm workflow próprio agendado; dependem de alguém
abrir o sistema no dia. A dedução de envios duplicados é garantida pela
tabela `notification_log` (e `task_request_log`, para a cobrança de
garantia/ART), então abrir o sistema mais de uma vez no mesmo dia nunca
reenvia o mesmo aviso.

### Configuração de e-mail (SMTP)

- Caixa usada: `licitacao@engemil.com.br` (KingHost, `smtp.kinghost.net`,
  porta 587, STARTTLS).
- Localmente: copie `configuracao_email.exemplo.bat` para
  `configuracao_email.bat` e preencha `SMTP_USER`, `SMTP_PASSWORD`,
  `SMTP_FROM` (e, se quiser uma cópia permanente, `SMTP_DEFAULT_CC`).
- Na nuvem: as mesmas chaves como variáveis `SMTP_*` nos Secrets do
  Streamlit Cloud (e nos Secrets do repositório GitHub, para os workflows
  agendados).
- O arquivo/variáveis são relidos a cada tela, teste e envio — não é
  preciso reiniciar o sistema depois de trocar a senha da caixa postal.

### Variáveis de ambiente relevantes

| Variável | Efeito |
|---|---|
| `TURSO_DATABASE_URL` / `TURSO_AUTH_TOKEN` | Liga o sistema ao banco hospedado (produção). Sem elas, usa SQLite local. |
| `GESTAO_DB_PATH` / `GESTAO_UPLOAD_DIR` | Caminho do banco/uploads locais (uso em desenvolvimento e testes). |
| `GESTAO_SESSION_IDLE_MINUTES` | Minutos de inatividade até o logout automático (padrão 30, mínimo 5). |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_USE_SSL`, `SMTP_DEFAULT_CC` | Configuração do envio de e-mail. |
| `GESTAO_SMTP_CONFIG` | Caminho de um `.bat` alternativo com as variáveis de SMTP acima (usado nos testes automatizados, para nunca usar a configuração real). |
| `GESTAO_PCP_API_KEY` | Chave de integração do Portal de Compras Públicas (ainda não obtida — ponto de extensão pronto em `bids.py`). |

### Instalação local (desenvolvimento/contingência)

Veja `README.md` para o passo a passo de instalação local no Windows
(ambiente virtual Python, `iniciar_sistema.bat`, instalação como serviço
do Windows via NSSM). Esse caminho local hoje serve principalmente como
ambiente de desenvolvimento/testes e contingência — o uso do dia a dia é
pela versão publicada na nuvem.

### Testes automatizados

`test_core.py` roda a suíte de regressão completa
(`.venv\Scripts\python.exe test_core.py`) — sempre com `GESTAO_SMTP_CONFIG`
apontando para um caminho inexistente (ou com `notifications.send_email`
substituído por um stub), para nunca disparar um e-mail real durante os
testes. Rode essa suíte antes de publicar qualquer alteração.

## 8. Como este manual é mantido atualizado

Este arquivo (`MANUAL_DO_SISTEMA.md`) faz parte do próprio código do
sistema, versionado no mesmo repositório Git. O compromisso, registrado
também em `CLAUDE.md`, é:

> **Toda atualização que muda, adiciona ou remove uma funcionalidade
> visível ao usuário atualiza este manual (a seção correspondente, o mapa
> do menu se uma página mudou de nome/sumiu/apareceu, e a seção 6 se um
> comportamento de e-mail mudou) na mesma tarefa em que a funcionalidade é
> alterada — junto do já estabelecido `VERSAO.txt` (changelog técnico,
> versão a versão) e do número de versão em `app.py`.**

`VERSAO.txt` continua sendo o **changelog histórico**, versão a versão,
com o "o que mudou e por quê" de cada entrega — este manual, em vez disso,
sempre descreve **o estado atual** do sistema, sem histórico. Quem quiser
entender a evolução de uma funcionalidade específica consulta o
`VERSAO.txt`; quem quer saber "como uso isso hoje" consulta este manual.

Este documento é também publicado como uma página web para consulta fácil
por quem não tem acesso ao repositório — a mesma atualização acima também
republica essa página:
<https://claude.ai/code/artifact/799b5250-ffd6-4e82-b449-137de7c7cffd>
