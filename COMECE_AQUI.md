# Cortes Clips

Esta é a pasta principal da ferramenta. Todo desenvolvimento, documentação, sessão, exemplo e corte novo deve ficar aqui. O caminho atual é `/caminho/para/cortes-clips`.

**Montagem padrão:** câmera do jogador no topo, título na junção, jogo na área inferior e legenda sobre o jogo na posição da referência do usuário. Leia `docs/PADRAO_MONTAGEM.md` antes de editar. As cores do desenho são apenas marcadores; o vídeo final usa os recortes reais da fonte. A primeira edição exige identificar e configurar as regiões da câmera e da gameplay.

## Usar com uma IA

Abra esta pasta no assistente com acesso ao computador e peça:

> Leia AGENTS.md, docs/FLUXO_PARA_IA.md e HOW-TO-CUT.md na íntegra. Use esta ferramenta para selecionar e editar os melhores trechos do vídeo que vou fornecer. Você fará as decisões editoriais; execute a captura, transcrição e renderização localmente pelos comandos existentes.

Para copiar uma instrução completa, use **PROMPT_PARA_OUTRAS_IAS.md**. Ela funciona como contexto de transferência e não depende do histórico desta conversa.

- **Codex:** a skill instalada `chat-clipper` já aponta para esta pasta e exige o protocolo completo `gameplay-live-clip-curation`. Pode pedir os cortes em português normalmente.
- **Outros assistentes com acesso a arquivos e terminal:** ler `AGENTS.md` e seguir o protocolo local. Não precisam da skill do Codex nem de uma chave de API para os comandos da ferramenta.
- **Chat sem acesso ao computador:** você executa os comandos e fornece `review.md`, a transcrição e as imagens de referência. A IA devolve o JSON de seleção, que você salva e manda renderizar. Um chat sem ferramentas locais não executa a edição sozinho.

O modelo responsável pela seleção é o modelo do assistente que estiver operando. O programa Python não chama o modelo por meio da assinatura do chat. Transcrição local usa Whisper. Vídeos e legendas são montados pelo FFmpeg.

## Conteúdo

| Arquivo/pasta | Uso |
|---|---|
| `README.md` | Manual completo, comandos e limites |
| `HOW-TO-CUT.md` | Protocolo integral obrigatório de curadoria: ordem, evidências, notas, comparação e montagem |
| `AGENTS.md` | Instruções neutras para agentes de IA |
| `CLAUDE.md`, `GEMINI.md` | Pontos de entrada para esses assistentes, apontando ao mesmo protocolo |
| `PROMPT_PARA_OUTRAS_IAS.md` | Texto para transferir o trabalho a outra IA |
| `docs/FLUXO_PARA_IA.md` | Protocolo, esquemas de dados e critérios de edição |
| `docs/ESTADO_ATUAL.md` | O que está implementado, validado e pendente |
| `docs/PADRAO_MONTAGEM.md` | Padrão visual obrigatório e como configurar os recortes da fonte |
| `layouts/`, `assets/references/` | Preset de composição e imagem original enviada pelo usuário |
| `chat_clipper/` | Código-fonte Python |
| `run.sh`, `setup.sh` | Executar e reconstruir o ambiente |
| `requirements.lock`, `pyproject.toml` | Dependências e empacotamento |
| `sessions/` | Capturas, vídeos importados, transcrições, planos e cortes |
| `examples/` | Vídeo sintético falado e cortes de demonstração |
| `tests/` | Testes automatizados |
| `skills/chat-clipper/` | Cópia da skill e runner do Codex |
| `graphify-out/` | Mapa estrutural Graphify, relatório e HTML |
| `docs/superpowers/` | Desenho, planos e decisões de implementação |
| `historico/` | Material de desenvolvimento e versão anterior arquivada; não é a versão para executar |
| `referencias/live-clipper-original/` | Arquivos do repositório original consultado e sua licença |
| `THIRD_PARTY_NOTICES.md` | Créditos e aviso de licença da referência original |

## Verificar e executar

```sh
cd "/caminho/para/cortes-clips"
./run.sh doctor
./run.sh list
```

O projeto foi validado neste Mac. Para transferir a outro computador, copie a pasta sem `.venv`, instale `uv` e FFmpeg/ffprobe e execute `./setup.sh`. O ambiente é reconstruído no novo local. Os modelos Whisper baixados ficam no cache padrão do Hugging Face, fora da pasta; outro computador pode precisar baixá-los novamente. As skills globais Superpowers, Graphify e Impeccable são preferências do Codex neste computador e não são pré-requisito para operar a ferramenta em outra IA.

O ambiente local e o protocolo não fazem publicação automática nem chamadas à API paga de um modelo. O uso do assistente continua sujeito ao seu plano. A seleção pela IA requer tarefa ativa; captura em segundo plano não significa modelo pensando indefinidamente.
