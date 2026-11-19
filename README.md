# Cortes Clips

Comece pela [instalação e uso](INSTALACAO.md).


**Pasta principal: `/caminho/para/cortes-clips`.** Comece por `COMECE_AQUI.md`. Para usar com outros assistentes de IA, leia `docs/FLUXO_PARA_IA.md` e copie `PROMPT_PARA_OUTRAS_IAS.md`. O código local não depende de um fornecedor de LLM; a integração com o Codex é uma das formas de operá-lo.

Ferramenta local para criar cortes de vídeos e lives **pelo chat de um assistente de IA**. O modelo da sessão escolhe os momentos e decide a edição. Python, Streamlink, Whisper e FFmpeg fazem captura, transcrição e montagem no computador. A integração inicial é com o Codex; outros assistentes podem usar o mesmo protocolo local.

## Usar aqui no chat

A skill `chat-clipper` está instalada no Codex. Você pode pedir:

Todos os cortes montados seguem o padrão de `docs/PADRAO_MONTAGEM.md`: câmera no topo, título na junção, gameplay embaixo e legenda sobre o jogo. A IA identifica as regiões da fonte e salva o perfil antes da renderização. A imagem do usuário está preservada em `assets/references/layout-usuario.png`.

A gameplay horizontal preenche a área por recorte centralizado. Depois de mostrar todos os cortes, a IA pergunta se algum deve ser adaptado para mostrar a tela inteira do jogo. Essa adaptação é individual (`gameplay_fit: contain`), mantendo o padrão dos demais.

> Use o Chat Clipper neste vídeo: `/caminho/video.mp4`. Siga HOW-TO-CUT.md inteiro e busque até três cortes, com45–90s como referência flexível, com contexto completo e legendas em português.

> Use o Chat Clipper para capturar o canal `CANAL` por 20 minutos. Durante esta tarefa, procure histórias e momentos engraçados e prepare os cortes.

> Mostre as sessões do Chat Clipper e retome a edição da sessão `ID`.

> No segundo corte, comece dois segundos antes e gere só a versão vertical.

Você fornece o canal, arquivo ou URL. O Codex executa os comandos, lê transcrição e imagens de referência, propõe ou produz os cortes e apresenta os arquivos aqui. A skill também pode ser invocada explicitamente como `$chat-clipper`.

## Como a IA participa

1. **Entrada:** vídeo local copiado para sessão própria, URL baixada por yt-dlp ou live Twitch capturada por Streamlink.
2. **Live:** segmentos curtos em buffer limitado; um snapshot copia os segmentos completos e gera um vídeo independente para editar.
3. **Transcrição:** faster-whisper local, com horários por palavra. Modelo padrão `small`; sem áudio não há legenda de fala.
4. **Revisão:** transcrição, tempos e frames de referência em `review.md` e `review.json`. O chat da Twitch, quando disponível, é apenas um sinal adicional.
5. **Seleção:** o modelo ativo desta conversa lê as evidências e escreve `selection.json` com início, fim, título e justificativa de cada trecho.
6. **Montagem:** FFmpeg valida o plano e o perfil de recortes e compõe câmera, título, jogo e legenda no preset vertical gamer. Pode acrescentar a versão na proporção original como cópia técnica se solicitada.

Não há chamada à API paga do ChatGPT. O uso da IA na conversa continua sujeito aos limites do seu plano do Codex. O Whisper continua sendo usado para transcrever; o ganho editorial vem do modelo do Codex, que pode considerar contexto e seus critérios em vez de apenas contar mensagens.

**A captura pode continuar em processo local, mas a seleção pela IA exige uma tarefa ativa do Codex.** Terminar a resposta não deixa um modelo pensando para sempre. O computador deve continuar ligado e conectado. A captura tem limite configurável, por padrão 120 minutos. Se você quiser acompanhamento durante a tarefa, indique o período; o Codex trabalha em ciclos. O buffer padrão preserva só os últimos cinco minutos, então pedir um momento antigo exige que um snapshot já tenha sido salvo.

## Saídas e retomada

As sessões ficam em `sessions/ID/` dentro deste projeto:

```text
session.json          origem, duração e estado de mídia
source.*              vídeo importado, ou mídia de snapshot
transcript.json       fala com horários por segmento e palavra
review.md / .json     material para a análise do Codex
selection.json        decisões editoriais da IA
renders/              resultados e manifesto (ver retorno do render)
```

Sessões de captura guardam também estado, logs, sinais de chat e segmentos do buffer. Não editar nem excluir os segmentos manualmente enquanto a captura estiver ativa. Os resultados e sessões persistem para outras conversas; o Codex recupera tudo com `list` e `status`.

A versão vertical é exportada em **720 × 1280**, seguindo a montagem obrigatória do usuário: câmera superior, título na transição, gameplay inferior e legenda na região fixa sobre a gameplay. É preciso definir as regiões reais da fonte com `composition`; a ferramenta não detecta rostos automaticamente. A versão chamada `horizontal` preserva a proporção da origem e é uma cópia técnica opcional. A transcrição pode conter erros; nomes próprios e legendas devem ser revisados. Seleção por contexto melhora os critérios, mas não garante viralização.

## Comandos técnicos

Você não precisa digitá-los se estiver operando pelo chat. Eles também permitem usar a ferramenta sem o Codex:

```sh
./run.sh doctor
./run.sh list
./run.sh import '/caminho/video.mp4'
./run.sh import 'https://site/video'
./run.sh start CANAL --buffer-minutes 5 --max-minutes 30
./run.sh status '/caminho/sessao-live'
./run.sh snapshot '/caminho/sessao-live'
./run.sh snapshot '/caminho/sessao-live' --seconds 60
./run.sh stop '/caminho/sessao-live'
./run.sh transcribe '/caminho/sessao-video' --language pt --model small
./run.sh review '/caminho/sessao-video'
./run.sh composition '/caminho/sessao-video' --camera '0,0,0.3,0.3' --gameplay '0.3,0.3,0.7,0.7'
./run.sh render '/caminho/sessao-video' --plan '/caminho/selection.json'
```

`snapshot` sem duração usa a cobertura disponível até o tamanho do buffer. Com `--seconds 60`, exige os 60 segundos completos; se ainda não existem, falha claramente. Para gerar o snapshot, são usados somente segmentos fechados. Portanto há atraso de aproximadamente um segmento em relação ao ponto mais recente da live.

Formato do plano:

```json
{
  "version": 1,
  "editor": "Codex (modelo desta conversa)",
  "clips": [
    {
      "id": "historia-01",
      "title": "Uma ideia completa",
      "start": 12.5,
      "end": 44.8,
      "reason": "A história termina antes da mudança de assunto.",
      "format": "vertical"
    }
  ]
}
```

Os tempos são relativos ao vídeo da sessão, em segundos. IDs devem ser seguros e únicos, os cortes devem ter de 1 a 180 segundos e não podem se sobrepor. Formatos: `both`, `horizontal`, `vertical`. O plano é validado contra a duração real antes de renderizar.

As coordenadas de `composition` acima são exemplos de sintaxe. A IA deve medi-las na fonte; não reutilizar esses valores em uma live arbitrária. Sem composição válida, exportação vertical é bloqueada. Leia `docs/PADRAO_MONTAGEM.md`.

## Instalação e manutenção

Neste computador, o ambiente `.venv` já foi preparado com Python 3.13. FFmpeg e ffprobe precisam estar no PATH. Para reconstruir o ambiente, instale `uv`, mantenha FFmpeg disponível e execute:

```sh
./setup.sh
./run.sh doctor
.venv/bin/python -m unittest discover -s tests -v
```

`requirements.lock` registra as versões exatas instaladas. O primeiro uso de um novo modelo Whisper pode baixar arquivos do Hugging Face; a transcrição roda localmente. `small` já foi preparado neste computador. Modelos maiores usam mais tempo e memória. A implementação usa CPU/int8 no Mac; não depende de uma GPU NVIDIA.

A skill instalada fica em `~/.codex/skills/chat-clipper/`; há uma cópia em `skills/chat-clipper/`. O `config.json` aponta para a pasta deste projeto. Se mover a ferramenta, atualize esse caminho na skill instalada.

## Limites e falhas

- Twitch e sites de vídeo podem exigir acesso ou mudar suas integrações. A ferramenta informa o erro; não contorna autenticação.
- Live interrompida tem tentativas limitadas de recuperação. Consulte `status` e os logs em caso de falha. Um snapshot não cruza silenciosamente lacunas da captura.
- Canal ou arquivo precisa ser informado pelo usuário. Não há monitoramento de canais por padrão.
- Captura exige espaço em disco; o buffer é limitado, mas snapshots e cortes salvos acumulam. A ferramenta não apaga suas sessões para liberar espaço.
- Vídeos longos podem levar tempo para transcrever. Os frames são amostras: ação rápida pode exigir inspeção adicional pelo Codex.
- O chat é coletado por amostragem, com até 15 mensagens por segundo. Suas contagens servem como sinais auxiliares e não representam necessariamente todo o volume de um canal grande; a relação com o vídeo tem alinhamento aproximado.
- Não há publicação em redes sociais. Use fontes que você tem autorização para editar e publicar.

## Desenvolvimento

O desenho e o plano estão em `docs/superpowers/`. A implementação usa Superpowers, testes automatizados e revisão independente. O mapa estrutural do código gerado com Graphify fica em `graphify-out/` quando disponível. A análise AST não chama uma API de IA nem envia seu código para um provedor externo.

O projeto original de referência é [akm72-bit/live-clipper](https://github.com/akm72-bit/live-clipper). Esta ferramenta implementa o fluxo operado pelo Codex em módulos próprios; o aviso de licença da referência está em `THIRD_PARTY_NOTICES.md`.

O protocolo editorial integral está em `HOW-TO-CUT.md`, obrigatório antes da seleção. `docs/CRITERIOS_EDITORIAIS.md` é seu ponto de entrada. A referência é45–90s com exceções justificadas; conversas gerais com o chat também são elegíveis. Aplicar as três passagens, evidências por critério e comparação para eliminar experiências repetitivas antes do plano técnico.
