# Gestão de Contratos ENGEMIL — versão 27

Dashboard interno em Python/Streamlit para centralizar contratos, aditivos, prazos,
repactuações, garantias, ARTs, responsáveis e documentos.

A interface oferece tema **Escuro** e **Claro**, com preferência individual por
usuário e logo adaptada ao fundo selecionado. A troca de aparência preserva a
página aberta e aplica o contraste correto também a tabelas, campos de seleção,
listas suspensas, abas, expansores, formulários e botões.

As tabelas de consulta utilizam um componente visual próprio: cabeçalho fixo,
linhas alternadas, destaques de situação, conteúdo sem abreviação e rolagem
responsiva. As tabelas destinadas à alteração dos dados permanecem editáveis,
mas seguem a mesma identidade visual.

O sistema permite cadastrar contratos manualmente ou importar novas versões da
planilha. Contratos encerrados podem ser arquivados e restaurados; o histórico,
os aditivos, as obrigações e os documentos permanecem preservados.

## Organização do menu

- **Visão geral:** dashboard dinâmico e responsivo com identidade ENGEMIL, valores
  completos, modalidades, projeção anual e os cinco maiores remanescentes em
  cartões de destaque. Dois gráficos interativos (Altair) mostram o valor
  vigente por centro de custo e o valor vencendo por mês nos próximos 12
  meses — passe o mouse para ver os valores exatos. Um controle explícito com ícone de lupa mostra cada
  contrato e campo pendente e oferece um atalho para abrir diretamente a ficha
  correta.
- **Contratos:** backlog consolidado com vigências, valores e remanescentes ano a
  ano, exportável em Excel e em PDF pronto para encaminhamento, com a aparência
  da planilha histórica utilizada pelos gestores. O PDF oficial contém apenas
  Item, Centro de custo, Contratante, Contrato, Início, Fim, Valor atual,
  Instrumento vigente e Remanescente total; as projeções anuais permanecem
  somente na tela e no Excel. Antes da geração, o usuário escolhe um responsável
  ativo ou cadastra outro diretor/gestor para assinatura e define a classificação
  por contratante, centro de custo, valor atual, remanescente, fim da vigência ou
  instrumento vigente. O PDF ajusta automaticamente o tamanho das linhas para
  caber a carteira inteira em uma página só (paginando normalmente apenas se
  isso exigir letras ilegíveis) e traz uma segunda página em A4 horizontal com
  um dashboard da carteira (indicadores, maiores contratos, vencimentos
  próximos, distribuição por centro de custo/categoria/status), pensado para
  impressão em preto e branco.
- **Ficha do contrato:** edição completa, aditivos, garantias e seguros, BDIs,
  regime de faturamento, sindicatos, datas-base, equipe, obrigações, ARTs, CNOs, documentos e
  arquivamento. Quando
  a modalidade for **ATA**, a ficha
  mostra automaticamente a área **Contratos decorrentes da ATA**, inclusive com
  aditivos e documentos próprios. As ARTs podem ser associadas ao contrato
  inicial, a um aditivo, à própria ATA ou a um contrato/aditivo decorrente da
  ATA.
- **Novo contrato:** cadastro direto, inclusive com múltiplos sindicatos e cargos.
- **Licitações:** carteira de licitações em que a ENGEMIL está participando,
  independente dos contratos já firmados — cadastro, filtros, indicadores,
  classificação (mapa de lances) com geração de imagem para envio aos gestores,
  consulta a editais/resultados publicados no PNCP e verificação automática de
  homologação por órgão já cadastrado.
- **SESMT:** cadastro de profissionais vinculados a contrato, exames
  ocupacionais (ASO) e treinamentos/certificados (NRs), com upload de
  documentos e indicadores de vencidos/vencendo em 30 dias. Tem um perfil de
  usuário próprio (`sesmt`), com edição restrita por padrão ao próprio módulo.
- **Exportações:** geração de Excel da visão geral, backlog, ficha e índices,
  além do Backlog ENGEMIL em PDF e da ficha contratual completa em Word.
- **Índices:** patrimônio líquido, receita, justificativas e declaração oficial
  em PDF A4 vertical. A relação de contratos ocupa a primeira página e as
  fórmulas, a justificativa e a assinatura ocupam a segunda.
- **Documentos padrões:** geração de Ofício, Carta de Preposto e Procuração em
  Word, cadastro de novos modelos, responsáveis pela assinatura e histórico
  de geração, aprovação e encaminhamento vinculado ao contrato.
- **Usuários:** ambiente exclusivo do administrador, com permissões independentes
  de consulta, lançamento, modificação e exclusão; desativação/exclusão de contas,
  redefinição do segundo fator, desbloqueio e revogação de sessões.

O `F5` restaura a conta e o mesmo menu por meio de uma sessão revogável cujo
token é armazenado somente como hash no banco. A sessão expira após 30 minutos
sem atividade. Ao clicar em **Sair** ou reiniciar o servidor, a próxima abertura
começa em **Visão geral**. Ao trocar de menu, a visualização volta ao topo.

Na tela **Contratos**, a data de início é sempre a data original do contrato. A
data final, o valor atual e o instrumento vigente são obtidos do último aditivo
ou apostilamento cadastrado. O remanescente é recalculado diariamente.

A **Visão Geral** considera somente contratos cuja vigência esteja válida na data
da consulta. Após o encerramento, o contrato permanece por 30 dias na situação
**Aguardando aditivo**. Se não houver prorrogação, é arquivado automaticamente.
Caso seja cadastrado posteriormente um aditivo com vigência válida, o contrato é
reativado sem perda do histórico.

O quadro **Remanescente previsto ano a ano** usa colunas proporcionais para o
ano, a barra e o valor completo em reais. Em telas estreitas, o valor passa para
a linha superior e a barra ocupa toda a largura, sem comprimir ou cortar o
conteúdo. O aviso de conferência cadastral deixou de ser apenas informativo:
ao expandi-lo, o usuário vê o contrato, o centro de custo, cada campo faltante,
a providência necessária e o botão **Abrir ficha para corrigir**.

Na **Ficha do contrato**, o sistema separa os dados de origem dos dados da
vigência atual e apresenta o tempo restante em anos, meses e dias. CCTs e
datas-base podem ser vinculadas ao instrumento contratual correspondente. Os
cartões ajustam automaticamente altura, quebra de linha e tamanho da fonte para
que datas, valores e descrições extensas permaneçam integralmente visíveis.
O objeto é exibido justificado, e a aba Resumo permite preparar uma ficha
institucional completa em Word. O relatório reúne os dados preenchidos de
todas as abas e omite campos sem informação.

Nos aditivos, o tipo **Outro** permite informar livremente o nome real do
instrumento, como Termo de Rerratificação, Ordem de Serviço ou Distrato.
A vigência em meses é calculada automaticamente a partir das datas inicial e
final, tanto nos instrumentos do contrato principal quanto nos contratos
decorrentes de ATA.

Na aba **ARTs**, cada registro possui nome, título e registro profissional,
número, datas, situação, descrição, documento vinculado e o instrumento
contratual de referência. Quando a ART é associada a um aditivo, a coluna
**ARTs vinculadas** desse instrumento é preenchida automaticamente com número e
situação. Os profissionais já cadastrados em qualquer contrato ficam disponíveis
para seleção e autopreenchimento de nome, título e registro. As ARTs são agrupadas
por profissional, preservando a ordem do primeiro cadastro e inserindo os novos
registros logo abaixo do respectivo histórico. Diferenças apenas de acento e
espaçamento não criam grupos duplicados. Registros anteriores permanecem
preservados e são sinalizados para associação, sem vínculos presumidos. A aba **CNO**, exibida
logo depois, mantém o número de inscrição da obra, data de cadastramento, início
da responsabilidade, área de atuação, observações e comprovantes anexados.

As grades editáveis de aditivos, aditivos de contratos decorrentes de ATA e
equipe exibem valores monetários por extenso no padrão brasileiro. Valores como
`R$ 22.763.546,65`, `22.763.546,65` ou `22763546.65` são convertidos sem alterar
o valor numérico armazenado. No cadastro de um novo contrato, a grade de equipe
também aceita valores monetários brasileiros. Valores como `R$ 3.500,00`,
`3.500,00` ou `3500.00` são gravados corretamente como salário-base. Registros
antigos que já tenham sido salvos com salário zerado são destacados para revisão
manual, pois o valor anterior não existe no banco para ser reconstruído.

No cadastro contratual inicial, o **valor atual** é automaticamente igual ao
**valor original**, pois ainda não existe instrumento posterior. O campo deixa
de exigir uma segunda digitação. A mesma regra vale para contratos decorrentes
de ATA. Registros existentes com valor atual zerado, valor original positivo e
nenhum aditivo são corrigidos automaticamente, sem interferir nos contratos que
já possuem instrumentos cadastrados.

Quando o órgão é informado como
`FUNDO NACIONAL DE DESENVOLVIMENTO DA EDUCAÇÃO - FNDE`, o sistema reconhece
automaticamente `FNDE` como sigla para os documentos padronizados e para a
numeração. O nome permanece completo nas telas e a geração evita resultados
duplicados como `... - FNDE - FNDE`.

### Garantias contratuais e seguros

A aba **Garantias e seguros** fica imediatamente após **Aditivos** e aceita
garantia contratual, garantia adicional, riscos de engenharia, responsabilidade
civil de obra ou profissional, seguro de vida/acidentes e tipos livres. Cada
registro pode ser vinculado ao contrato inicial, a um aditivo ou a contratos e
aditivos decorrentes de uma ATA.

O controle registra modalidade, fundamento, valor exigido, seguradora ou banco,
corretora, apólice, registro SUSEP, segurado, cossegurado, emissão, vigência,
prêmio e prazo para apresentação. O formulário foi sintetizado para utilizar o
percentual sobre a base contratual ou o valor definido diretamente no instrumento.

Cada apólice admite múltiplas coberturas, com LMI, vigência, franquia/POS e
observações. Endossos, renovações, substituições e cancelamentos ficam em
histórico próprio, sem sobrescrever a apólice original. Documentos podem ser
associados à garantia principal ou a um endosso específico.

O sistema aponta documentos ausentes, garantia vencida e vigência inferior à do
instrumento contratual. A coluna **Garantias vinculadas**
dos aditivos é preenchida automaticamente. O agendador diário envia alertas de
vigência em 60, 30 e 15 dias, além do prazo definido para apresentação do
documento. As informações também são incluídas no Excel e na ficha completa em
Word.

Na aba **Editar**, o controle antigo de índice de reajuste foi substituído por
**Datas do orçamento**. Cada contrato aceita várias referências, com data,
descrição e observações próprias. O vencimento genérico da garantia foi removido,
pois cada garantia ou seguro possui vigência própria na aba dedicada.

### BDI e regime de faturamento

A aba **BDI** fica imediatamente após **Garantias e seguros**. O contrato pode ser indicado
como onerado, desonerado ou ainda não definido. Cada contrato aceita quantas
composições forem necessárias, com identificação e referência próprias, como
**BDI 1 — Mão de obra**, **BDI 2 — Materiais** e **BDI 3 — Serviços**.

Há dois métodos de cálculo:

- **Soma direta:** custos indiretos + lucro + tributos.
- **Fórmula composta:** considera Administração Central, Seguros, Riscos,
  Garantias, outros custos indiretos, Despesas Financeiras, Lucro e Tributos.

Na fórmula composta, o usuário escolhe entre truncar a fração em quatro casas ou
arredondar o percentual em duas casas. PIS, COFINS, ISS, CPRB e outros tributos
são detalhados separadamente. A composição e o percentual calculado também são
incluídos na exportação Excel e na ficha contratual em Word.

## Instalação no Windows

1. Instale o Python 3.11 ou superior.
2. Abra o Prompt de Comando dentro desta pasta.
3. Crie e ative um ambiente virtual:

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

4. Importe a planilha inicial:

```bat
python importer.py "02_ANALISE_CRITICA_DE_CONTRATOS(2).xlsx" --substituir-aditivos
```

5. Inicie o sistema:

```bat
streamlit run app.py
```

O navegador abrirá em `http://localhost:8501`.

No dia a dia, o mais simples é usar `iniciar_sistema.bat` (cuida do
ambiente virtual e das dependências sozinho). Outros scripts prontos:

- **`reiniciar_sistema.bat`** — encerra o processo que estiver ouvindo na
  porta 8501 (sem precisar abrir o Gerenciador de Tarefas), limpa o
  `__pycache__` e inicia de novo. Útil depois de atualizar os arquivos.
- **`instalar_servico_windows.bat`** — instala o sistema como serviço do
  Windows (via NSSM), para ele iniciar sozinho com o computador e não
  depender de deixar um terminal aberto. Depois de instalado, use
  `reiniciar_servico.bat` para aplicar atualizações, e
  `remover_servico_windows.bat` para reverter ao modo manual. Exige
  baixar o NSSM separadamente (instruções no próprio script).

## Primeiro acesso

- E-mail: `admin@engemil.local`
- Senha temporária: `Alterar@123`

Crie os usuários autorizados no menu **Usuários**. O sistema armazena as senhas
com PBKDF2 e nunca em texto puro.

## Sessão segura e atualização da página

O login permanece válido quando o usuário atualiza a página com `F5`. A
aplicação utiliza um identificador aleatório no navegador e armazena no banco
somente seu hash, nunca a senha nem o token original. O identificador é
vinculado ao navegador, renovado durante o uso e revogado no botão **Sair**.

Após **30 minutos sem atividade**, a sessão é encerrada automaticamente e o
usuário precisa entrar novamente. Interações com campos, botões, menus e a
própria atualização da página contam como atividade. A verificação ocorre
periodicamente, mesmo que a tela permaneça aberta. O último menu utilizado
também é restaurado após o `F5`.

Ao alterar a senha, as outras sessões abertas daquela conta são encerradas. O
tempo padrão pode ser ajustado pelo administrador com a variável de ambiente
`GESTAO_SESSION_IDLE_MINUTES`, nunca inferior a cinco minutos.

## Autenticação em duas etapas

O 2FA fica desabilitado inicialmente. Ao criar ou administrar um usuário, o
administrador decide se o segundo fator será exigido. Quando habilitado, o QR
Code é compatível com Google Authenticator, Microsoft Authenticator e
aplicativos TOTP equivalentes. Administradores podem desabilitar a exigência ou
redefinir o segundo fator de um usuário que perdeu o aparelho.

Os códigos dependem do relógio do servidor e do celular. Mantenha data, hora e
fuso horário em modo automático nos dois equipamentos. O sistema aceita uma
pequena tolerância de sincronização de até 60 segundos.

## Alertas automáticos de obrigações e repactuação

Ao informar a próxima repactuação de uma CCT, o sistema cria uma obrigação com
90 dias de antecedência e tenta enviar e-mail ao responsável administrativo ou
ao engenheiro. O SMTP deve estar configurado conforme a seção de e-mail.

Cada obrigação pode ter um e-mail principal, vários endereços em cópia ou um
grupo de distribuição. Também são configuráveis a antecedência do primeiro
alerta e a frequência das cobranças. Enquanto o status não for **Concluída** ou
**Cancelada**, o sistema continua enviando lembretes e identifica automaticamente
os prazos vencidos.

Para conferir os alertas diariamente no Windows, abra o **Agendador de Tarefas**
e crie uma tarefa diária apontando para:

```text
C:\Sistemas\GestaoContratos\executar_alertas.bat
```

O arquivo `iniciar_sistema.bat` também pode ser usado para abrir o sistema sem
digitar os comandos no terminal. A biblioteca usada para preservar a sessão
após o `F5` acompanha o pacote na pasta `vendor`, permitindo sua instalação
local mesmo sem conexão com a internet.

O arquivo `verificar_integridade.bat` realiza uma conferência somente de leitura
no banco e informa salários zerados, ARTs sem título profissional, contratantes
sem sigla explícita, anexos não localizados e aditivos com datas inválidas. Ele
não altera cadastros e pode ser executado antes de cada backup ou atualização.

A execução diária de `executar_alertas.bat` também aplica o arquivamento
automático, mesmo que nenhum usuário abra o sistema naquele dia.

## Perfis

- **Administrador:** acesso integral, gestão das permissões e exclusão definitiva
  de contratos mediante confirmação, além do histórico das 100 atividades mais
  recentes.
- **Usuário comum:** o administrador escolhe, módulo a módulo, se poderá
  visualizar, editar ou excluir itens.
- **SESMT:** perfil dedicado ao Serviço Especializado em Engenharia de
  Segurança e em Medicina do Trabalho — por padrão, só tem permissão de
  lançar/editar no módulo SESMT (os demais módulos ficam apenas para
  visualização, como qualquer perfil). Pode ser ampliado manualmente por
  usuário, como qualquer outro perfil.

Na Ficha do contrato, a permissão **Excluir itens** controla instrumentos,
sindicatos, cargos, benefícios, obrigações, ARTs, CNOs e documentos anexados. Arquivos
excluídos são enviados para a pasta `trash` para permitir recuperação
administrativa.

O módulo **Documentos padrões** segue essas mesmas permissões. O administrador
também pode substituir modelos e cadastrar signatários, enquanto os demais
usuários só geram ou atualizam documentos se receberem permissão de edição.

## Modelos Word e VBA

Os arquivos `.dotm` originais permanecem disponíveis para download no sistema,
preservando as macros VBA existentes. Para a geração automatizada no servidor, o
sistema utiliza uma cópia `.docx` segura do mesmo layout e substitui os campos
padronizados sem executar macros. O documento é gerado em Word editável, com
numeração sequencial e registro no histórico.

O LibreOffice é necessário somente se o administrador cadastrar um novo modelo
em `.dotm` ou `.dotx` e o sistema precisar convertê-lo para a cópia operacional
`.docx`. O Backlog em PDF é gerado diretamente pela aplicação e não depende do
LibreOffice.

O arquivamento continua sendo a opção recomendada para contratos encerrados,
pois é reversível e mantém o histórico. A exclusão definitiva deve ser usada
somente para registros indevidos ou realmente obsoletos.

## Alertas por e-mail

O painel sempre exibe os prazos. A versão 21 envia três tipos de comunicação:

- cobranças das obrigações cadastradas em **Prazos e obrigações**, respeitando
  antecedência e frequência;
- alertas de repactuação;
- avisos ao engenheiro responsável quando faltarem até 30 dias e, depois, até
  15 dias para o encerramento da vigência atual.

Para usar diretamente a caixa postal `licitacao@engemil.com.br` da KingHost:

1. Copie `configuracao_email.exemplo.bat`.
2. Renomeie a cópia para `configuracao_email.bat`.
3. Mantenha `SMTP_HOST=smtp.kinghost.net`, `SMTP_PORT=587` e
   `SMTP_USE_SSL=0` para utilizar STARTTLS.
4. Preencha `SMTP_USER` e `SMTP_FROM` com `licitacao@engemil.com.br`.
5. Preencha `SMTP_PASSWORD` somente com a senha atual da caixa postal da
   KingHost. Nunca envie essa senha junto com o sistema.
6. Se desejar uma cópia permanente para a gestão, preencha
   `SMTP_DEFAULT_CC`.
7. Execute `testar_email.bat` ou use **Ficha do contrato > Prazos e
   obrigações > Configuração e teste dos alertas por e-mail**.
8. Execute `configurar_alertas_automaticos.bat` uma única vez como
   administrador do Windows. A tarefa diária será criada para 08:00.

O arquivo `configuracao_email.bat` é a fonte prioritária do aplicativo. Ele é
relido a cada atualização da tela, teste e envio, inclusive pelos alertas de
obrigações, repactuações e encerramentos. Isso impede que configurações antigas
herdadas pelo processo continuem aparecendo após a edição do arquivo. O painel e
`testar_email.bat` exibem servidor, porta, segurança, usuário e remetente
efetivos, mas nunca mostram a senha. Restrinja o acesso ao arquivo no Windows; o
configurador diário tenta limitá-lo automaticamente ao usuário atual e ao SYSTEM.

Além da cópia global, cada obrigação aceita seus próprios destinatários em cópia
ou um grupo de e-mail, separados por vírgula ou ponto e vírgula.

Cada aviso de encerramento é registrado em `notification_log`. O sistema não
repete o mesmo aviso para o mesmo contrato, data final e destinatário. Se um novo
aditivo alterar a vigência, a nova data passa a ter seu próprio ciclo de 30 e 15
dias.

## Aditivos e CNOs

As linhas históricas `INICIAL / CONTRATO` importadas da planilha não são
aditivos. A migração da versão 21 preserva suas datas em campos próprios do
contrato original e remove somente essas linhas da aba **Aditivos**.

Em contratos classificados como **ATA**, cada CNO deve apontar para um contrato
decorrente da ata. Em contratos comuns, o CNO continua vinculado diretamente à
ficha principal. O vínculo também aparece nas exportações e na ficha Word.

## Identificação profissional

Todas as páginas, inclusive a tela de login, apresentam no rodapé a
identificação do responsável pela
concepção e desenvolvimento da aplicação: Rodrigo de Sousa da Silva, Engenheiro
de Software, CREA-DF nº 36849/D-DF e RNP nº 0724248897.

## Padrão dos relatórios

Backlog, ficha contratual, declaração de índices e documentos produzidos pelos
modelos da empresa são mantidos em folha **A4 vertical**. O sistema não cria
seções em paisagem para acomodar tabelas: os dados são reorganizados em colunas
compactas. Os documentos institucionais preservam Calibri 11 e o papel timbrado
e continuam sendo gerados exclusivamente em Word, permitindo ajustes antes do
encaminhamento. O Backlog é um relatório de consulta e é gerado diretamente em
PDF, com tipografia compacta, totais, assinatura selecionada e rodapé no padrão
usado pelos gestores. O critério de ordenação e o signatário ficam registrados
no histórico de geração.

## Implantação recomendada

Para uso por várias pessoas, execute o sistema em um servidor interno ou nuvem
com HTTPS, backup diário do arquivo `gestao_contratos.db` e da pasta `uploads`.
Em uma fase posterior, o SQLite pode ser trocado por PostgreSQL e o login pode
ser integrado ao Microsoft 365/Entra ID.
