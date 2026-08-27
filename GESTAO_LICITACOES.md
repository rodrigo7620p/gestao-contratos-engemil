# Módulo Licitações — GESTÃO_CONTRATOS_ENGEMIL (a partir da V29)

## O que o módulo faz

Acompanha as licitações em que a ENGEMIL está participando, separado da
carteira de contratos já firmados. Cada licitação tem: número do processo,
**UASG**, edital/pregão, plataforma, órgão, UF, objeto, modalidade, valor
estimado, status, data da disputa, nosso lance final, desconto e
classificação. É possível vincular uma licitação a um contrato já
cadastrado quando ela é convertida (homologada e assinada).

A tela mostra indicadores (quantidade em andamento, taxa de sucesso, valor
estimado e valor de lance em disputa), filtros por status/plataforma/texto,
cadastro, edição e uma aba de classificação por licitação.

## Edição completa (a partir da V33)

Todos os campos do cadastro — não só status/lance/classificação — podem
ser completados ou corrigidos depois, na aba "Resumo e edição" de cada
licitação: número do processo, edital, plataforma, órgão, objeto, UF,
modalidade, valor estimado, datas de disputa/proposta e responsável pelo
acompanhamento. Útil para quando alguma informação fica pendente no
cadastro inicial (ex.: uma licitação cadastrada às pressas, só com número
do processo e órgão, para depois ser completada com calma).

## Classificação e imagem para os gestores

A aba "Classificação" permite digitar ou colar a tabela exportada da
plataforma do pregão (sequência, empresa, lance final, desconto), marcando
qual linha é a ENGEMIL. A partir dela, o botão gera uma **imagem PNG** no
padrão visual da ENGEMIL (mesma cor institucional dos relatórios em Word),
com a linha da ENGEMIL destacada — pronta para baixar e encaminhar aos
gestores, exatamente no espírito do relatório de classificação que a
plataforma de pregão já exporta.

A imagem é gerada com Pillow, usando as fontes DejaVu Sans embutidas em
`assets/fonts/` (licença permissiva, redistribuível) para não depender de
fontes instaladas no Windows.

## Integração com o PNCP (Portal Nacional de Contratações Públicas)

A aba "Consultar contratações publicadas no PNCP" chama a API pública e
gratuita do PNCP (sem necessidade de chave/token), endpoint:

```
GET https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao
    ?dataInicial=AAAAMMDD&dataFinal=AAAAMMDD&codigoModalidadeContratacao=N
    &uf=UF&cnpj=CNPJ_DO_ORGAO&pagina=1
```

Documentação oficial: https://pncp.gov.br/api/consulta/swagger-ui
Manual de Integração: https://www.gov.br/pncp/pt-br/acesso-a-informacao/manuais

**Importante — o que o PNCP mostra e o que ele não mostra:**
O PNCP publica editais e, depois de concluída a disputa, o resultado
homologado. Ele **não** expõe o mapa de lances/classificação de uma
disputa em andamento — isso é operacional da plataforma que está rodando
o pregão (Compras.gov.br "Sala de disputa", Portal de Compras Públicas,
BLL, Licitanet etc.), não do PNCP. Por isso a busca no PNCP serve para
localizar e conferir editais/resultados, mas a classificação em si
continua sendo cadastrada manualmente (ou colada do relatório da
plataforma) na aba "Classificação".

Esta chamada não foi testada com uma requisição real durante o
desenvolvimento porque o ambiente usado para programar não tem acesso à
internet pública — apenas a documentação oficial foi conferida. **Teste a
busca no PNCP assim que atualizar o sistema** e, se algum parâmetro tiver
mudado desde a última verificação (agosto/2026), ajuste
`pncp_search_contratacoes()` em `bids.py` consultando o Swagger acima.

**Limitação confirmada na V30 — por que não existe "puxar automaticamente
todas as participações da ENGEMIL":** conferi o Manual de Integração
oficial do PNCP (Consultas API v1.0) linha por linha. Todos os serviços de
consulta (`contratacoes/publicacao`, `contratacoes/proposta`, `atas`,
`contratos`) filtram por **CNPJ do órgão comprador** — nenhum deles aceita
filtrar por CNPJ do fornecedor/participante. Ou seja, a API pública do
PNCP não permite perguntar "em que licitações o CNPJ 04.768.702/0001-70
está participando" de forma direta; ela é organizada pelo órgão, não pelo
fornecedor. Isso não é uma limitação da nossa implementação — é uma
limitação da API do governo, confirmada também por outros desenvolvedores
tentando o mesmo tipo de busca.

**O que a V30 automatiza, dentro do que é tecnicamente possível:** para
cada licitação cadastrada com o CNPJ do órgão preenchido, o botão
"Verificar no PNCP" (na aba "Resumo e edição") consulta
`GET /v1/contratos?cnpjOrgao=...&dataInicial=...&dataFinal=...` — que
retorna os contratos publicados por aquele órgão no período — e filtra no
próprio sistema os que têm `niFornecedor` igual ao CNPJ da ENGEMIL
(constante `COMPANY_CNPJ` em `bids.py`, hoje `04768702000170`). Se
encontrar, oferece marcar a licitação como "HOMOLOGADA - VENCEDORA" com o
valor e o número de controle PNCP preenchidos automaticamente.

Isso **confirma resultados de processos já homologados** por órgãos que
você já cadastrou — não descobre novas participações nem acompanha
disputas em andamento, porque essa informação simplesmente não existe na
API pública do PNCP antes da homologação.

## Como conseguir o que foi pedido de verdade: descoberta automática de participações

Para "reconhecer automaticamente todas as licitações em que a ENGEMIL está
participando" — incluindo disputas em andamento, não só resultados já
homologados — a única fonte de dados que realmente sabe disso é a
plataforma onde a ENGEMIL faz login e envia propostas (Portal de Compras
Públicas, Compras.gov.br, BLL, Licitanet), porque é ali que a
participação é registrada no momento em que acontece. Nenhuma dessas
plataformas publica isso numa API pública sem autenticação — faz sentido,
já que é informação vinculada à conta da empresa, não dado público de
transparência.

Caminhos possíveis, em ordem de esforço:
1. **Portal de Compras Públicas** (abaixo) — tem API própria com dados de
   processo/participação, mas exige solicitar a chave.
2. **Compras.gov.br** tem um "Painel do Fornecedor" acessível após login
   com o certificado/gov.br da empresa, mas não encontrei uma API pública
   equivalente para automação — precisaria ser avaliado à parte, com mais
   tempo de pesquisa, se isso for prioridade.
3. Continuar cadastrando manualmente ao decidir participar de uma
   licitação (como já é hoje) — e deixar o PNCP confirmar o resultado
   automaticamente quando o processo é decidido, via o botão descrito
   acima.

## Relatório de licitações vigentes em PDF (V34)

No final da lista de licitações, o botão "Exportar licitações do filtro
atual em PDF" gera um relatório em A4 horizontal, sempre em uma página
(mesmo princípio de ajuste automático já usado no Backlog oficial — só
pagina se isso tornar o texto ilegível), no mesmo espírito do
`01_CONTROLE_DE_EDITAIS.xlsx` que a ENGEMIL já mantém. As colunas são
escolhidas por você antes de gerar (processo, UASG, edital, órgão, UF,
escopo, plataforma, modalidade, objeto, valores, desconto, classificação,
status, data da disputa, responsável), e o relatório respeita os filtros
já aplicados na tela (status, plataforma, escopo, texto pesquisado).
Desde a V35, **Objeto e Escopo já vêm pré-selecionados por padrão**, para
o relatório identificar do que se trata cada certame sem precisar
escolher manualmente.

## Três opções claras de estrutura + gerador de itens (V42)

A partir de um exemplo real do TJDF (Pregão 15/2026, com 3 grupos —
Grupo 1 · 5 itens, Grupo 2 · 5 itens, Grupo 3 · 10 itens), deixei mais
explícita a diferença entre os três jeitos de estruturar um certame ao
cadastrar:

1. **Individual** — um único item para todo o certame (comportamento
   mais simples, já existia).
2. **Vários itens individuais** — o mesmo processo licitatório tem
   vários itens, mas cada um concorre e é classificado separadamente
   (sem grupo).
3. **Grupo(s) com itens** — cada grupo reúne vários itens; a disputa de
   lances acontece item por item, mas quem vence é decidido pelo
   **valor total do grupo inteiro** — exatamente como o Compras.gov.br
   funciona. É o caso do exemplo do TJDF.

Ao escolher a opção 2 ou 3, o primeiro grupo/item que você cadastrar na
aba Grupos/Itens já vem com o campo "Tipo" pré-marcado corretamente
(Item avulso ou Grupo), sem precisar trocar manualmente.

**Gerador de linhas "Item 1, Item 2..."**: ao detalhar os itens de um
grupo pela primeira vez, um atalho novo pergunta "Gerar quantos itens?"
e já cria as linhas nomeadas, prontas para você preencher só quantidade
e valor unitário — testado recriando os 5 itens do Grupo 1 do exemplo
do TJDF, com soma automática batendo exatamente com o valor do portal
(R$ 592.810,56).

## Seta ▲ para lances acima do estimado e nome de arquivo padronizado (V41)

Revisando um exemplo real do TCU (Pregão 53/2026), notei que os
participantes com lance ACIMA do valor estimado apareciam com "0,00%"
na classificação — o que escondia a informação real (na prática, essas
empresas ofertaram um valor MAIOR que o estimado, não um desconto).

- **Corrigido**: agora aparece o percentual de quanto ficou acima do
  estimado, em laranja, com uma seta ▲ (ex.: "▲ 9,26%") — bem diferente
  visualmente do desconto normal (vermelho). Vale tanto para a imagem
  de classificação quanto para o relatório "Licitações vigentes" em PDF.
- **Nome do arquivo da imagem**: o download agora segue o padrão
  `CLASS_<SIGLA DO ÓRGÃO>_<CERTAME>_<UASG>.png` (ex.:
  `CLASS_TCU_53-2026_30001.png`), para identificar o arquivo pelo nome
  sem precisar abri-lo. Quando a classificação é de um grupo/item
  específico, o nome do grupo é acrescentado no final.

## Estrutura do certame já no cadastro, itens detalhados e mais ajustes (V40)

### Estrutura do certame escolhida já ao cadastrar

Ao abrir "Cadastrar nova licitação", a primeira pergunta agora é **"Como
este certame será cadastrado?"**:
- **Individual** — um valor estimado único para todo o certame (o
  comportamento de sempre).
- **Por grupo(s) e/ou item(ns)** — quando escolhida, os campos de
  quantidade/valor do formulário principal desaparecem (ficam para depois,
  por grupo/item), e assim que a licitação é salva, o formulário de
  cadastro de grupo/item já abre automaticamente logo abaixo — não é mais
  preciso primeiro salvar, procurar a aba, e só então lembrar de detalhar
  os grupos.

### Itens dentro de cada grupo/item (como o Compras.gov.br)

A aba Grupos/Itens agora também tem, para cada grupo/item cadastrado, uma
seção **"Itens deste grupo/item"** — uma tabela onde você lança cada
material/serviço com sua quantidade solicitada, valor estimado unitário
e (quando já tiver o resultado) o nosso valor ofertado unitário —
exatamente como aparece no Compras.gov.br (ex.: LUMINÁRIA, LÂMPADA LED,
PLUGUE, CABO ELÉTRICO FLEXÍVEL, cada um com sua própria quantidade e
valor). **O valor estimado e o valor ofertado do grupo/item passam a ser
somados automaticamente a partir dessas linhas** — não precisa mais somar
na mão. Testado com um exemplo real de 5 itens: o valor estimado somado
bateu exatamente com o valor total mostrado no portal.

Cada grupo/item também ganhou um campo **Tipo** (Grupo ou Item avulso),
para identificar visualmente qual é qual na listagem.

Se preferir não detalhar item por item, o campo de valor total único
(já existente desde a V37) continua funcionando normalmente — os itens
são um detalhamento opcional.

### Horário da disputa

Novo campo, ao lado da data da disputa, no cadastro e na edição de
licitações — e disponível como coluna no relatório "Licitações vigentes"
em PDF.

### CNPJ do órgão padronizado

O campo "CNPJ do órgão" (edição de licitação) agora sempre mostra o valor
já formatado (XX.XXX.XXX/XXXX-XX) depois de salvo — você digita só os
números, o sistema cuida da máscara.

### Textos dos filtros em português

Os campos de seleção múltipla (filtros de Status, Plataforma, Escopo,
Contrato etc.) mostravam "Choose options" em inglês quando vazios —
corrigido em todo o sistema para "Selecione...".

## Estrutura do certame já no cadastro e detalhamento por item (V40)

Revisando com mais atenção o Compras.gov.br (a partir de um exemplo real
do TJDF, Pregão 15/2026, Grupo 1 com 5 itens), fiz dois ajustes
estruturais importantes:

1. **A pergunta "Individual ou por grupo/item?" agora acontece já no
   cadastro**, não só depois de editar. Ao abrir "Cadastrar nova
   licitação", a primeira decisão é essa — se "Por grupo(s) e/ou
   item(ns)" for escolhido, os campos de quantidade/valor somem do
   formulário principal (porque cada grupo/item vai ter os seus
   próprios) e a licitação recém-criada já é sinalizada para você
   completar na aba Grupos/Itens.
2. **Detalhamento item por item dentro de cada grupo/item**, replicando
   exatamente a estrutura do portal: um grupo (ex.: "Grupo 1 · 5 itens")
   reúne vários itens (ex.: LUMINÁRIA, LÂMPADA LED, PLUGUE, PLUGUE, CABO
   ELÉTRICO FLEXÍVEL), cada um com sua própria quantidade solicitada,
   valor estimado unitário e nosso valor ofertado unitário. O valor
   estimado e o valor ofertado do grupo/item passam a ser **somados
   automaticamente** a partir desses itens (quantidade × valor unitário
   de cada linha) — exatamente como o "Valor estimado (total)" e "Valor
   proposta (total)" do portal. Testei com os valores exatos do exemplo
   do TJDF e o total bateu certinho.
   - Se preferir não detalhar item por item, o campo de valor total
     manual (já existente desde a V37) continua disponível — só fica
     bloqueado quando já existem itens cadastrados, para não haver dois
     números conflitando.
3. **Horário da disputa**: novo campo ao lado da data, no cadastro, na
   edição, na listagem e como coluna do relatório em PDF.
4. **CNPJ do órgão formatado**: digite só os números, o campo mostra
   formatado (XX.XXX.XXX/XXXX-XX) ao reabrir para editar.

## Excluir licitação, filtro por período e Grupos/Itens já no cadastro (V39)

- **Excluir licitação**: na aba "Resumo e edição" de cada licitação, um novo
  expansor "Excluir esta licitação" remove definitivamente o processo, seus
  grupos/itens e toda a classificação — com checkbox de confirmação. Use
  para desistência de participar ou cadastro feito por engano; para
  registrar uma disputa perdida, prefira mudar o Status.
- **Filtro por período**: a carteira de licitações agora tem "Data da
  disputa — de" e "— até", para ver só o que aconteceu numa janela
  específica (por exemplo, só o mês corrente).
- **Grupos/Itens acessível já ao cadastrar**: depois de cadastrar uma nova
  licitação, ela já aparece automaticamente selecionada logo abaixo, com um
  aviso apontando para a aba Grupos/Itens — não é mais preciso primeiro
  salvar e depois procurar onde editar para incluir os grupos.

## Relatório "Licitações vigentes": sigla do órgão e quebra de linha (V39)

Dois ajustes de legibilidade no PDF, mantendo sempre uma página A4
horizontal:

- **Coluna ÓRGÃO**: mostra a sigla (ex.: "CONAB") em vez do nome completo
  ("COMPANHIA NACIONAL DE ABASTECIMENTO - CONAB"), reconhecida
  automaticamente a partir do texto entre parênteses ou após o hífen no
  final do nome do contratante — mesma lógica já usada na imagem de
  classificação. Quando não há sigla reconhecível, o nome completo aparece
  em várias linhas (ver item abaixo), nunca cortado ou espremido.
- **Coluna OBJETO** (e ÓRGÃO, quando sem sigla): em vez de diminuir a
  fonte para caber no espaço — o que tornava o texto ilegível —, o texto
  agora quebra em até 3 linhas, com a linha da tabela crescendo em altura
  conforme necessário. Só corta com reticências se ainda assim não couber
  em 3 linhas. Testado com 25 licitações simultâneas: o relatório
  continua numa página quando cabe, e pagina automaticamente (mantendo a
  mesma fonte legível) quando não cabe — nunca mais espreme tudo numa
  única página ilegível.

## Funcionários nominais e importação de planilha do RH (V39)

Na Ficha do contrato, aba **"Equipe e cargos"**, nova seção **"Funcionários
nominais"** — diferente da tabela de cargos já existente (que é um
planejamento por quantidade, ex.: "Servente — 5 vagas"), esta guarda o
nome de cada pessoa efetivamente alocada no contrato.

### Importação de planilha (Excel/CSV)

1. Envie a planilha como o RH exportar — não precisa reformatar.
2. O sistema tenta reconhecer automaticamente qual coluna é qual (nome,
   cargo, centro de custo, CPF, admissão, salário-base), mas **você sempre
   confirma o mapeamento antes de importar** — nada é gravado sem
   confirmação explícita.
3. Se a planilha tiver uma coluna de centro de custo, só as linhas que
   correspondem ao centro de custo do contrato aberto são importadas — as
   demais são ignoradas e informadas na tela (ex.: "1 linha de outro
   centro de custo foi ignorada"). Sem essa coluna, todas as linhas da
   planilha são consideradas deste contrato.
4. **A planilha em si nunca é salva no sistema** — só os dados
   reconhecidos e confirmados por você viram registros.
5. Também é possível cadastrar um funcionário manualmente, sem planilha.

### Integração com o SESMT

Ao cadastrar um novo profissional no menu SESMT, se o contrato escolhido
já tiver funcionários nominais cadastrados (importados ou manuais), aparece
a opção **"Importar dados de um funcionário já cadastrado na equipe deste
contrato"** — evita redigitar nome e cargo de quem já está na equipe.
Só os dados relevantes ao SESMT (nome e cargo) são reaproveitados — não
há vazamento de outras informações entre os módulos.

## Grupos/Itens e os três campos de valor (V37)

Duas melhorias estruturais pedidas depois de ver o exemplo real da CONAB:

### Três campos de valor, em vez de dois

Antes só existiam "Quantidade" e "Valor estimado". Agora:
- **Quantidade solicitada** (ex.: 3.750)
- **Valor estimado (unitário)** (ex.: R$ 322,0300 — como aparece no edital)
- **Valor estimado (total)** (ex.: R$ 1.207.612,50 — é este que o sistema
  usa para calcular o desconto na classificação)

Se você deixar o total em branco (0) mas preencher quantidade e unitário,
o sistema calcula o total sozinho (quantidade × unitário) — tanto no
cadastro quanto na edição.

### Grupos/Itens (quando o certame tem mais de um item)

Muitos pregões do Compras.gov.br têm vários itens ou grupos de itens no
mesmo processo — cada um com seu próprio valor estimado, e a disputa
acontece por grupo, não pelo processo inteiro (ex.: "Grupo 1 · 3 itens",
"Grupo 2 · 2 itens", ou vários itens individuais). Nova aba **"Grupos/Itens"**
em cada licitação:

- Cadastre um grupo/item para cada linha do jeito que aparece no portal:
  nome (ex.: "Grupo 1"), quantidade de itens que ele reúne (informativo),
  quantidade solicitada, valor estimado unitário e total (com o mesmo
  cálculo automático do total).
- A aba **Classificação** passa a ter um seletor "Qual grupo/item deseja
  classificar?" sempre que houver mais de um grupo/item cadastrado — cada
  grupo tem sua própria classificação (colada ou editada), seu próprio
  desconto (calculado a partir do valor estimado DAQUELE grupo, não do
  processo inteiro) e sua própria imagem para os gestores (com o nome do
  grupo no título/objeto).
- **Se o certame tiver um único item**, não precisa cadastrar nada nesta
  aba — tudo continua funcionando exatamente como antes, direto na
  licitação (nenhuma mudança de comportamento para o caso mais comum).
- Testado com um cenário de dois grupos: confirmei que a classificação de
  um grupo nunca aparece no outro nem no nível geral da licitação, e que
  a aba Resumo e edição do processo continua isolada de cada grupo (quem
  usa Grupos/Itens acompanha o resultado agregado, grupo a grupo, na
  própria aba Grupos/Itens).

### Como isso preserva o que já foi lançado

Essa mudança é **estritamente aditiva** no banco: duas colunas novas
(`estimated_unit_value` em Licitações, `bid_lot_id` na Classificação) e
uma tabela nova (`bid_lots`) — nenhuma tabela ou coluna existente foi
alterada, e nenhum registro já cadastrado precisa ser tocado. Uma
licitação cadastrada antes desta versão (como a própria licitação da
CONAB que vocês acabaram de lançar) continua funcionando exatamente como
estava — os Grupos/Itens são um recurso a mais, não uma migração
obrigatória.

## Valor unitário × global e três bugs reais corrigidos (V36)

Analisando os prints que vocês enviaram, encontrei e corrigi três problemas
reais no que tinha sido entregue na V35:

1. **"DESCLASSIFICADA" aparecendo no lugar do nome da empresa na imagem
   gerada.** Causa: o parser de blocos não reconhecia a linha
   "Desclassificada" como uma marcação de situação — ela acabava entrando
   na extração do nome da empresa. Corrigido: agora a situação
   (Desclassificada/Inabilitada/Desistente) é reconhecida separadamente,
   removida do texto antes de extrair o nome, e gravada no campo Situação
   de cada empresa.
2. **Desconto de 99,98% sem sentido.** Causa raiz: o valor do lance nesse
   formato do Compras.gov.br vem por **unidade** ("Valor ofertado
   (unitário)"), mas o valor estimado cadastrado no sistema é sempre o
   **total** do processo — comparar um contra o outro dá um "desconto"
   absurdo. Corrigido com o novo campo **Quantidade estimada** (cadastro e
   edição): quando o rótulo colado diz "(unitário)", o sistema multiplica
   automaticamente pela quantidade antes de calcular o desconto. Testado
   com o exemplo real de vocês (piso vinílico da CONAB): R$ 200,00
   unitário × 3.750 = R$ 750.000,00 global, resultando em 37,89% de
   desconto (contra os 99,98% que apareciam antes).
3. **Empresas desclassificadas atrapalhando a numeração da classificação.**
   Corrigido: o sistema agora reordena automaticamente a lista depois de
   colar — todas as empresas classificadas primeiro (renumeradas 1, 2, 3…
   como se as desclassificadas não estivessem lá), e as desclassificadas/
   inabilitadas/desistentes vão para o final, mantendo nome, CNPJ e valor
   ofertado, mas com a situação bem sinalizada (na imagem: nome riscado,
   linha esmaecida).

**Percentual de desconto colado junto do valor**: o sistema já reconhecia
apenas o valor; agora também reconhece quando o portal cola o percentual
junto, entre parênteses, no formato `R$ 17.096.139,3259 (34,50 %)`. Esse
percentual só é usado quando a licitação ainda não tem valor estimado
cadastrado (nesse caso não há como calcular por conta própria); quando o
valor estimado existe, o sistema sempre recalcula do zero, para garantir
consistência.

**Preenchimento automático da aba Resumo e edição**: depois de colar ou
salvar a classificação, se a ENGEMIL estiver na lista, o sistema já
atualiza sozinho — na aba Resumo e edição — o nosso lance final, o
desconto e a posição de classificação, sem precisar digitar de novo.

**Identificação da licitação na imagem gerada**: o título deixou de
mostrar só o número do processo e passou a mostrar sigla do órgão +
edital/pregão + UASG + valor estimado (ex.: "CONAB · 13/2026 · UASG
135100 · Estimado: R$ 1.207.612,50"), para identificar rapidamente de
qual certame se trata, como pedido.

**Responsável pelo acompanhamento preenchido automaticamente**: ao abrir
"Cadastrar nova licitação", os campos Responsável e E-mail já vêm
preenchidos com o nome e o e-mail de quem está logado — mesmo espírito
já usado no cadastro de ARTs. Continuam editáveis, caso a licitação seja
acompanhada por outra pessoa.

## Escopo (Obra/Manutenção/Terceirização) e revisão da planilha de controle (V35)

Revisei o `01_CONTROLE_DE_EDITAIS.xlsx` novamente com esse pedido em
mente. Adicionei o campo **Escopo** (Obra / Manutenção / Reforma /
Terceirização / ATA / Consórcio / Outro) no cadastro, na edição, na
listagem e como filtro — mesma lista já usada na categoria dos contratos,
para manter o vocabulário consistente para quando uma licitação vira
contrato.

**Outras colunas da planilha que identifiquei mas não implementei
agora** (para vocês decidirem se vale a pena):
- **HORA** da disputa (a planilha tem hora separada da data; hoje só
  guardamos a data);
- **MODO DE DISPUTA** (Aberto / Fechado / Aberto-Fechado / Randômico) —
  diferente de "Modalidade" (Pregão Eletrônico, Concorrência etc.), que
  já existe. Não confundir os dois: modalidade é o tipo de licitação,
  modo de disputa é a dinâmica de lances dentro dela.

Não implementei esses dois porque não foram pedidos explicitamente e
prefiro confirmar que valem a pena antes de mexer de novo no cadastro —
é rápido de adicionar se vocês confirmarem que fazem falta no dia a dia.

## Classificação (mapa de lances) — colar do portal e imagem para gestores (V34, ampliado na V35)

A aba "Classificação" de cada licitação agora tem três formas de preencher
a tabela de empresas participantes:

1. **Colar do portal**: copie a classificação do Compras.gov.br, PNCP ou
   de qualquer outro portal e cole no campo "Colar classificação copiada
   do portal". O sistema reconhece automaticamente **dois formatos
   diferentes**, sem precisar escolher qual:
   - uma linha por empresa (sequência, empresa, CNPJ opcional, lance
     final), separada por tabulação ou por espaços — o formato de
     tabela resumida (SEQ / EMPRESAS / LANCE FINAL / DESCONTO);
   - o formato "em blocos" de algumas telas do Compras.gov.br, com várias
     linhas por empresa (CNPJ, selos como "ME/EPP" e "Programa de
     integridade", nome, UF, "Valor ofertado (unitário)" / "Valor
     negociado (unitário)" e os valores) — testado com o texto real que
     a ENGEMIL colou, reconhecendo CNPJ, nome, UF e valor ofertado de
     cada empresa corretamente, ignorando os selos.
   Em ambos os casos, **o desconto não é lido do texto colado — é sempre
   recalculado automaticamente** a partir do valor estimado já cadastrado
   nesta licitação (aba Resumo e edição), garantindo que o percentual
   mostrado seja sempre consistente com o valor estimado oficial, e não
   com um percentual que o portal eventualmente tenha exibido com outra
   base de cálculo. Por isso, **o valor estimado precisa estar
   preenchido antes de colar a classificação**.
2. **Edição manual** na tabela, linha a linha — inclui CNPJ e
   **situação** (Classificada / Desclassificada / Inabilitada / Desistente),
   para registrar quando uma empresa é desclassificada ao longo do
   certame.
3. A **imagem gerada para os gestores** (botão "Baixar imagem") já usa a
   identidade visual da ENGEMIL (mesma cor institucional dos relatórios em
   Word) em vez das cores do portal de origem. A linha da ENGEMIL é
   destacada automaticamente (reconhecida pelo CNPJ 04.768.702/0001-70 ou
   pelo nome), e empresas desclassificadas aparecem com o nome riscado,
   linha esmaecida e a situação indicada.

## Achado sobre automação total via Compras.gov.br (pesquisado, não implementado)

Durante a pesquisa desta versão, encontrei uma página real do Comprasnet
que devolve o resultado por fornecedor de um pregão a partir da UASG e do
número do pregão:

```
https://comprasnet.gov.br/livre/pregao/FornecedorResultadoDecreto.asp
    ?f_coduasg=<UASG>&f_numPrp=<ANO+NÚMERO>&f_tpPregao=E&prgcod=<CÓDIGO_INTERNO>
```

Testei o acesso a essa página e ela realmente retorna os dados (empresa,
CNPJ, valores por item, vencedor) — confirmando que a automação total que
vocês pedem é tecnicamente possível para pregões do Compras.gov.br.
**Não implementei a automação completa nesta versão**, por três motivos
que quero deixar claros:

1. Essa página exige um `prgcod` (código interno do pregão) que não é o
   número do pregão nem a UASG — seria preciso um passo adicional para
   descobri-lo a partir desses dois dados, e não encontrei essa consulta
   documentada.
2. É uma página HTML antiga (ASP, do sistema legado do Comprasnet, anterior
   à Lei 14.133/2021), não uma API com contrato estável — o formato pode
   mudar sem aviso, e "raspar" HTML é inerentemente mais frágil que
   consumir uma API oficial. Para pregões já migrados para a Lei
   14.133/2021 (cada vez mais comuns), essa página legada pode nem
   existir, e a informação equivalente estaria espalhada no PNCP.
3. Construir e validar esse fluxo com segurança (localizar o `prgcod`,
   tratar mudanças de formato, cobrir tanto pregões antigos quanto os já
   migrados para a Lei 14.133/2021) é um trabalho de engenharia maior do
   que consigo entregar testado com confiança nesta sessão.

**Recomendação prática enquanto isso não é automatizado**: o recurso de
colar do portal (acima) já resolve boa parte do ganho de produtividade —
em vez de digitar cada linha, é só copiar a tabela do Compras.gov.br e
colar. Se no futuro vocês quiserem que eu avance na automação completa via
scraping dessa página legada, ou se conseguirem localizar uma
documentação oficial do `prgcod`, me avisem — dá para retomar esse ponto
especificamente.

## Integração com o Portal de Compras Públicas (pendente de chave)

O Portal de Compras Públicas (plataforma usada no exemplo de classificação
que originou este módulo) tem uma API própria — a "Biblioteca de Dados" —
que devolve os dados dos processos realizados na própria plataforma,
incluindo resultado/lances. Diferente do PNCP, o acesso **exige solicitar
uma chave de integração**:

1. Acesse o formulário de solicitação de chave da Biblioteca de Dados do
   Portal de Compras Públicas (procure por "Portal de Compras Públicas
   Biblioteca de Dados API" — o link muda ocasionalmente, por isso não foi
   fixado aqui).
2. Preencha com os dados da ENGEMIL. A chave (PublicKey) é enviada por
   e-mail em até 7 dias úteis.
3. Quando a chave chegar, defina a variável de ambiente
   `GESTAO_PCP_API_KEY` (mesmo padrão de `configuracao_email.bat`) e
   implemente a chamada real dentro de `portal_compras_publicas_search()`
   em `bids.py`, seguindo o formato de requisição/resposta que a própria
   plataforma detalhar junto com a chave.

Até lá, a função existe como ponto de extensão e retorna um erro
explicativo se for chamada sem a chave configurada — ela não é usada pela
interface hoje.

## Outras plataformas (BLL, Licitanet, ComprasNet)

Não encontrei API pública documentada para BLL Compras ou Licitanet no
momento desta implementação. O ComprasNet/Compras.gov.br federal tem
serviços de consulta em dados abertos (diferentes do PNCP), que podem ser
avaliados depois se fizer sentido para o seu volume de disputas nessas
plataformas. Por ora, licitações dessas plataformas são cadastradas
manualmente como as demais — o campo "Plataforma" já cobre todas elas.

## Estrutura de dados

- `bid_processes`: uma linha por licitação/processo.
- `bid_rankings`: uma linha por empresa participante, vinculada à
  licitação (`bid_process_id`).

Nenhuma tabela de contrato existente foi alterada. O vínculo com contratos
é opcional (`bid_processes.contract_id`, `ON DELETE SET NULL` — apagar um
contrato nunca apaga o histórico da licitação).

## Permissões

O módulo usa a chave `bids` no sistema de permissões já existente
(`user_permissions`), com o mesmo comportamento padrão dos demais módulos:
visualização liberada por padrão, criação/edição de acordo com o perfil do
usuário (operador, gestor, engenheiro) ou ajuste manual em
Usuários e permissões.
