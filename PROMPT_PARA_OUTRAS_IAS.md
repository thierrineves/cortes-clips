# Prompt para outra IA

Copie o texto abaixo. Se estiver em outro computador, substitua o caminho inicial pelo local onde copiou a pasta.

---

Tenho uma ferramenta de cortes de vídeo na pasta:

`/caminho/para/cortes-clips`

Quero que você opere essa ferramenta usando o seu próprio modelo para analisar e selecionar os trechos, e os comandos locais para transcrever e gerar os vídeos. Leia primeiro `AGENTS.md`, `COMECE_AQUI.md`, `docs/ESTADO_ATUAL.md` e `docs/FLUXO_PARA_IA.md` dentro dessa pasta; leia também `HOW-TO-CUT.md` inteiro antes de selecionar cortes. Não dependa da conversa que criou o projeto.

Se você tem acesso a arquivos e terminal, execute o fluxo existente. Comece com `./run.sh doctor` e `./run.sh list`. Peça o vídeo, URL ou canal apenas se eu ainda não o tiver informado. Não reconstrua a ferramenta nem substitua por um serviço pago.

Siga integralmente as três passagens de HOW-TO-CUT.md, preencha as notas com evidências e compare os candidatos antes de escolher. Analise a transcrição e as imagens de referência. Escolha trechos compreensíveis e com conclusão, respeitando quantidade, duração e temas que eu pedir. Escreva um `selection.json` válido, com horários relativos ao vídeo da sessão e justificativa de cada corte. Depois renderize, confira os arquivos e me entregue os resultados com caminhos completos. Use o formato de plano e os comandos documentados no projeto.

**Siga obrigatoriamente `docs/PADRAO_MONTAGEM.md`:** vídeo vertical9:16, câmera real do jogador no topo, título na junção, gameplay na área inferior e legenda sobre o jogo na região definida. As cores do desenho são só marcadores. Inspecione a fonte e use o comando `composition` para configurar os recortes antes de renderizar. Não invente câmera nem use um layout alternativo por conta própria. A entrega padrão é `format: vertical`.

A gameplay será horizontal. Preencha a área do modelo com recorte `cover` sempre centralizado. Depois de apresentar todos os cortes, pergunte se algum precisa mostrar a tela inteira do jogo; só então adapte individualmente os indicados com `gameplay_fit: contain`, preservando o restante da montagem.

Se você não tem acesso ao computador, diga claramente essa limitação e me guie na execução dos comandos. Vou fornecer os arquivos de revisão e você devolve o JSON de seleção. Não diga que gravou, assistiu ou exportou algo que não executou ou verificou.

Mantenha tudo relacionado à ferramenta nesta pasta, preserve os vídeos originais e não publique resultados sem meu pedido. Para lives, só analise enquanto a tarefa estiver ativa; não prometa monitoramento pela IA depois de terminar a resposta.

Minha fonte e meus critérios são: **[cole aqui o vídeo/URL/canal e o pedido de cortes]**.

---

## Protocolo editorial obrigatório

Ler **HOW-TO-CUT.md na íntegra antes de selecionar ou revisar cortes**, inclusive ao retomar sessões. Esse arquivo é a fonte canônica da skill `gameplay-live-clip-curation`; o resumo abaixo não o substitui.

Ordem: leitura integral e restrições do usuário → descoberta de candidatos → revisão e delimitação com gancho, contexto, desenvolvimento e payoff → cinco notas com evidências localizadas → comparação e descarte de experiências repetitivas → ficha de curadoria → plano técnico → montagem e conferência.

Duração de referência do vídeo final: **45–90 segundos, flexível**. Momentos fortes e completos podem durar menos ou mais, com justificativa concreta. Não alongar material fraco para atingir um mínimo. Gameplay e conversas gerais com o chat são elegíveis se entregarem interesse, contexto e conclusão. A quantidade pedida é uma meta: entregar apenas os que qualificarem, inclusive zero, sem completar com candidatos fracos ou repetitivos e sem capturar outra janela por conta própria.

Cada um dos cinco critérios exige nota individual, evidência concreta, fonte, intervalo e tipo de evidência. Sem comprovação, marcar não verificado; não aprovar por nota total presumida. Registrar candidatos aprovados e rejeitados, motivos, IN/payoff/OUT, duração final e sequência de montagem em `curadoria.md` ou `curadoria.json` dentro da sessão. Respeitar o formato integral da ficha do HOW-TO-CUT.

Distinguir tempos do VOD, da mídia do snapshot e do vídeo final. Cortes internos, antecipação de reação e zoom dentro dos painéis são permitidos editorialmente, preservando sentido e causalidade; confirmar suporte técnico antes de exportar. O CLI atual aceita um intervalo contínuo por corte e tem limite técnico de1–180s; isso não é uma regra editorial de duração e não implementa uma montagem descontínua. Não declarar recursos executados se estiverem apenas descritos no plano.
