# Atualização segura do sistema

Este pacote corresponde à **versão 27** e foi preparado sobre a versão 26
consolidada. A atualização reorganiza ARTs, simplifica garantias e cria o controle
de múltiplas datas de orçamento sem excluir contratos, instrumentos, usuários,
documentos ou históricos.

Esta versão mantém as melhorias anteriores, preserva os dados históricos das
garantias e acrescenta agrupamento/autopreenchimento de profissionais nas ARTs,
prevenção de duplicidade e datas de orçamento editáveis.

## 1. Encerrar o sistema

No terminal em que o Streamlit está aberto, pressione `Ctrl + C`.

## 2. Fazer o backup

Copie para uma pasta de backup:

```text
gestao_contratos.db
uploads
trash
configuracao_email.bat
```

Esses itens contêm os cadastros e os documentos. Não os substitua pelos arquivos
do pacote novo.

## 3. Extrair a nova versão

Use preferencialmente o pacote
`ATUALIZACAO_GESTAO_CONTRATOS_ENGEMIL_V27_SEM_BANCO.zip`. Os arquivos desse ZIP
ficam diretamente na raiz, sem criar outra pasta `GESTÃO_CONTRATOS_ENGEMIL`.

Extraia o conteúdo diretamente dentro da pasta da instalação atual e confirme
**Substituir os arquivos no destino**. O pacote incremental não contém
`gestao_contratos.db`, `uploads`, `trash` nem `.venv`; por isso os cadastros,
anexos e o ambiente atual são preservados.

Não copie a pasta extraída para dentro de outra pasta com o mesmo nome, pois isso
cria uma instalação aninhada e o Streamlit continua executando os arquivos
antigos.

## 4. Atualizar as dependências

Abra o terminal na pasta do sistema:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 5. Atualizar a estrutura do banco

```powershell
python -c "from db import init_db; init_db()"
```

Esse comando apenas cria os novos campos e tabelas. Os contratos existentes são
preservados.

## 6. Iniciar

```powershell
streamlit run app.py
```

Também é possível executar `iniciar_sistema.bat`.
Na primeira abertura da versão 27, esse arquivo verifica as bibliotecas de
geração do PDF e de sessão do navegador e instala as dependências
automaticamente se alguma ainda não estiver no ambiente virtual. O componente
de sessão segura acompanha o pacote na pasta `vendor` e pode ser instalado sem
internet.

## 7. Configurações após a atualização

1. Escolha o tema **Escuro** ou **Claro** no menu lateral. A preferência ficará
   salva para o usuário. A troca mantém a página atualmente aberta.
2. Em **Índices**, confira patrimônio líquido, receita bruta, justificativa e
   dados do signatário; depois gere a declaração oficial em **PDF** e confira as
   duas páginas A4 verticais.
3. Em **Usuários**, configure para cada pessoa as permissões de consultar,
   lançar, modificar e excluir em cada módulo.
4. Habilite o 2FA somente para quem deverá utilizá-lo.
5. Em **Ficha do contrato > Equipe e cargos**, informe o salário mínimo do ano.
6. Preserve seu `configuracao_email.bat`. Para uma instalação nova, copie
   `configuracao_email.exemplo.bat`, informe a nova senha da caixa postal e
   restrinja o acesso ao arquivo no Windows. O modelo já contém KingHost,
   porta 587, STARTTLS e o remetente `licitacao@engemil.com.br`.
7. No Agendador de Tarefas do Windows, execute `executar_alertas.bat` diariamente.
   Essa tarefa envia alertas e cobranças recorrentes, identifica obrigações
   vencidas, alerta garantias/seguros aos 60, 30 e 15 dias e arquiva contratos
   encerrados há mais de 30 dias.
8. Em **Usuários**, conceda acesso ao novo módulo **Documentos padrões** somente
   às pessoas autorizadas.
9. Em **Documentos padrões > Modelos e assinaturas**, revise os modelos e os
   responsáveis cadastrados antes da primeira emissão.
10. Em **Contratos**, prepare o **Backlog ENGEMIL em PDF** e confirme a tabela,
    os totais, o rodapé e a folha A4 vertical.
    O relatório terá somente Item, Centro de custo, Contratante, Contrato,
    Início, Fim, Valor atual, Instrumento vigente e Remanescente total.
    Antes de gerar, selecione um responsável ativo ou cadastre outro diretor ou
    gestor para assinatura e escolha o critério de ordenação.
11. Em **Ficha do contrato > Resumo**, prepare a ficha completa em Word.
    Campos em branco não serão incluídos no relatório.
12. Em **Ficha do contrato > BDI**, defina o regime de faturamento e cadastre as
    composições aplicáveis a mão de obra, materiais ou serviços.
13. Em **Ficha do contrato > Equipe e cargos**, revise o aviso de salários
    zerados. Esses valores não ficaram armazenados na versão anterior e precisam
    ser informados novamente.
14. Em **Ficha do contrato > ARTs**, complete o novo campo **Título
    profissional** nos registros existentes.
15. Em **Ficha do contrato > CNO**, cadastre o número de inscrição, as datas, a
    área de atuação e, se necessário, anexe o comprovante.
16. Em **Ficha do contrato > ARTs**, edite cada registro antigo sinalizado como
    “Não associado — revisar” e selecione o contrato inicial ou o aditivo correto.
    O sistema não cria associações históricas por suposição.
17. Em **Ficha do contrato > Aditivos**, confirme que o valor aparece como
    `R$ 22.763.546,65` e que a coluna **ARTs vinculadas** apresenta as ARTs
    cadastradas no instrumento correspondente.
18. Em **Ficha do contrato > Garantias e seguros**, cadastre uma garantia de
    teste, vincule-a a um aditivo, confira os valores exigido e garantido, inclua
    uma cobertura e anexe um documento. Volte à aba **Aditivos** e confirme o
    preenchimento automático da coluna **Garantias vinculadas**.

## 8. Geração de documentos

Os modelos originais `.dotm` com VBA estão preservados no pacote e podem ser
baixados no próprio sistema. A geração integrada utiliza os equivalentes `.docx`
e registra número, modelo, contrato, autor, situação, encaminhamento e protocolo.
Os documentos institucionais são gerados em Word para permanecerem editáveis e
evitar conflitos de conversão no computador ou servidor. O Backlog e a declaração
de Índices são relatórios oficiais de consulta e são disponibilizados diretamente
em PDF pronto para encaminhamento.

## 9. Conferências recomendadas

1. Abra **Contratos** e confirme que **Início** corresponde ao contrato original
   e **Fim** ao instrumento vigente mais recente.
2. Abra uma **Ficha do contrato** e confira os quadros “Contrato original” e
   “Vigência atual”.
3. Teste um usuário comum para verificar se os módulos sem permissão não
   aparecem no menu.
4. Gere a declaração de Índices em PDF e revise as duas páginas antes de assiná-la.
5. Abra uma ficha classificada como **ATA** e confira a área **Contratos
   decorrentes da ATA**.
6. Ainda na ficha, alterne entre **Claro** e **Escuro** e confirme que a ficha
   permanece aberta e que o campo **Abrir ficha do contrato**, as abas e as
   tabelas continuam legíveis.
7. Confira o bloco **Top 5 contratos mais vantajosos**. Cada contrato agora é
   exibido em um cartão responsivo com valor atual, remanescente, modalidade e
   instrumento vigente.
8. Em **Ficha do contrato > Editar**, confira o formato `DD/MM/AAAA`, os valores
   em `R$ 0,00` e a ordem Engenheiro responsável/Responsável administrativo.
9. Gere um Ofício de teste em **Documentos padrões**, baixe o Word e
   atualize o registro para **Encaminhado**, incluindo o protocolo.
10. Em **Índices**, confirme que patrimônio líquido e receita aparecem como
    `R$ 139.259.969,94`, sem números comprimidos ou quebrados.
11. Em **Equipe e cargos**, cadastre um cargo de teste e remova-o usando uma
    conta com permissão **Excluir itens**.
12. Em **Prazos e obrigações**, cadastre o e-mail principal, uma cópia ou grupo,
    envie uma cobrança manual e confira a chegada da mensagem.
13. Na tela de login, confira a identificação profissional no rodapé.
14. No tema **Claro**, confira a palavra do botão de upload e as setas dos campos
    de seleção. Ambos devem permanecer visíveis.
15. Em **Visão geral**, confira a modalidade **MANUTENÇÃO** em diferentes
    larguras de tela; a palavra não deve ser quebrada no meio.
16. Em **Ficha do contrato > BDI**, confira os cenários de soma direta e fórmula
    composta, inclusive o resultado de 32,49% com truncamento e 22,23% com
    arredondamento nos exemplos de referência.
17. Gere a ficha em Word e confirme a seção **Custos Indiretos, Tributos e
    Lucro — BDI**, com regime, aplicação e parcelas de cada composição.
18. Cadastre um contrato de teste com salário no padrão `R$ 3.500,00` e confirme
    que a Ficha exibe `R$ 3.500,00`, sem converter o valor para zero.
19. Use um contratante terminado em ` - FNDE`, gere um Ofício e confirme que a
    sigla aparece uma única vez no órgão, no contrato e na numeração.
20. Cadastre um aditivo com datas inicial e final e confirme que a quantidade de
    meses foi preenchida automaticamente.
21. Cadastre uma ART com título profissional e um CNO; depois gere a ficha em
    Word e confira as duas seções.
22. Em **Visão geral**, ative **EXIBIR PENDÊNCIAS E ABRIR FICHAS**, confira os
    campos apontados e use o botão para abrir automaticamente a ficha.
23. Confira **Remanescente previsto ano a ano** em tela cheia e em uma janela
    estreita; anos, barras e valores em reais devem permanecer proporcionais.
24. Gere o Backlog em PDF e confira se a orientação é A4 vertical, os contratos
    aparecem em linhas alternadas e os totais estão completos.
25. Gere um Backlog assinado por Matheus e outro por Regiton e confira o nome,
    cargo, registro profissional e CPF disponíveis em cada cadastro.
26. Teste as ordenações por contratante, centro de custo, valor, remanescente,
    fim da vigência e instrumento; a coluna Item deve ser renumerada.
27. Abra o FNDE 337/2026 e confirme que o valor atual passou a corresponder ao
    valor original de R$ 817.706,44.
28. Entre no sistema, abra a **Ficha do contrato** e pressione `F5`; o usuário
    deve continuar autenticado e o mesmo menu deve permanecer aberto.
29. Edite um contrato e volte à **Visão geral**. A confirmação da conferência
    cadastral deve aparecer uma única vez e desaparecer após oito segundos.
30. Deixe uma sessão de teste sem qualquer interação por 30 minutos; o sistema
    deve encerrar o acesso e solicitar novo login.
31. Clique em **Sair** e pressione `F5`; a sessão revogada não deve ser
    restaurada.
32. Abra um aditivo com valor superior a um milhão e confirme o uso de pontos
    para milhares e vírgula para centavos, tanto na grade de aditivos quanto na
    equipe e nos contratos decorrentes de ATA.
33. Cadastre uma ART vinculada a um aditivo, volte à aba **Aditivos** e confirme
    o preenchimento automático do número e do status da ART. Depois altere o
    vínculo e confirme que a ART aparece somente no instrumento selecionado.

## Relatórios em A4 vertical

- A declaração de Índices é gerada diretamente em PDF, sempre em duas páginas
  A4 verticais.
- O Backlog ENGEMIL segue a tabela compacta da análise crítica histórica, com
  logo, cabeçalho, vigências, valores, instrumento vigente, remanescente, totais
  e rodapé.
- A ficha contratual reúne resumo, instrumentos, BDIs, contratos de ATA,
  sindicatos, equipe, benefícios, obrigações, ARTs, CNOs e documentos.
- Os documentos Word mantêm papel timbrado e Calibri 11; o Backlog usa tipografia
  compacta própria da tabela histórica. Todos permanecem em página A4 vertical.
- A ficha contratual e os documentos padrões continuam em Word editável. O
  Backlog e a declaração de Índices são gerados diretamente em PDF A4 vertical.

## Regra do arquivamento automático

- O dashboard considera somente vigências válidas.
- Do primeiro ao trigésimo dia após o fim, o contrato fica como **Aguardando
  aditivo**.
- Após 30 dias sem nova prorrogação, o contrato é arquivado.
- A ficha arquivada permanece editável.
- Um aditivo posterior com nova data final válida reativa o contrato
  automaticamente.

## Atualização da versão 21

- Os registros `INICIAL / CONTRATO` importados da planilha deixaram de aparecer
  como aditivos. A migração preserva as datas originais em campos próprios e
  mantém os valores e as vigências efetivas.
- Novas importações ignoram a linha do contrato inicial na lista de aditivos.
- CNOs de contratos classificados como ATA agora exigem o vínculo com um dos
  contratos decorrentes da ata.
- A tabela de Contratos ganhou a coluna **Prazo restante**, com texto como
  “Falta 1 dia”, “Falta 2 meses” ou “Falta 1 ano e 3 meses”.
- O engenheiro responsável recebe um aviso na janela de 30 dias e uma
  confirmação na janela de 15 dias antes do encerramento.
- Os avisos registram data final, destinatário e tipo no histórico para impedir
  duplicidade. Um novo aditivo reinicia o ciclo usando a nova data final.
- A aba **Prazos e obrigações** ganhou diagnóstico do SMTP, envio de mensagem
  de teste e histórico dos alertas de encerramento.
- Foram incluídos `testar_email.bat` e
  `configurar_alertas_automaticos.bat`.

### Conferências adicionais da versão 21

32. Abra um contrato originalmente importado e confirme que a aba **Aditivos**
    começa no primeiro termo aditivo/apostilamento real, sem a linha
    `INICIAL / CONTRATO`.
33. Confira nos quadros da ficha que as datas originais e a vigência atual não
    mudaram após essa limpeza.
34. Em uma ficha classificada como ATA, cadastre um contrato decorrente e
    confirme que o formulário do CNO exige esse vínculo.
35. Abra **Contratos** e confira a coluna **Prazo restante** em contratos com
    menos de 30 dias, vários meses e mais de um ano.
36. Configure o Gmail, envie uma mensagem por **Enviar e-mail de teste** e
    confirme o remetente `licitacao@engemil.com.br`.
37. Execute `executar_alertas.bat` duas vezes. O segundo processamento não deve
    repetir um aviso já registrado para a mesma vigência.
38. Execute `configurar_alertas_automaticos.bat` e confira no Agendador de
    Tarefas do Windows a tarefa **ENGEMIL - Alertas Contratuais**, às 08:00.
