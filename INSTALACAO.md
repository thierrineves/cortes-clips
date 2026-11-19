# Instalação e uso

Abra um terminal na pasta clonada. Tenha uv, FFmpeg e ffprobe disponíveis no PATH, com suporte a legendas ASS. Os scripts foram desenvolvidos para macOS com shell POSIX.

```sh
./setup.sh
./run.sh doctor
```

Abra a pasta clonada no Codex ou em outro agente com acesso ao terminal local. Peça: “Leia AGENTS.md e HOW-TO-CUT.md na íntegra. Selecione os melhores momentos desta fonte, registre a curadoria e execute o plano com o Cortes Clips.”

Para instalar as skills no Codex, copie as duas pastas de `skills/` para o diretório de skills do seu usuário e ajuste `chat-clipper/config.json` para o caminho absoluto do clone. A instalação das skills é opcional quando o agente consegue ler o projeto diretamente.

Em um chat sem terminal, envie o HOW-TO-CUT.md e o material de revisão produzido localmente. O chat pode devolver a curadoria e o plano JSON, que você salva e passa ao comando `./run.sh render SESSAO --plan selection.json`.

## Curadoria e execução

Use o GPT‑6.2 Sol para analisar a fonte e decidir o que entra. Registre evidências, ordem editorial e tempos no plano. Execute diretamente no FFmpeg via CLI quando o plano estiver completo. Se houver trabalho de adaptação ou diagnóstico e um modelo econômico estiver disponível para delegação, forneça a ele apenas o plano, os caminhos da sessão, o perfil de composição e os critérios de conferência. A configuração de modelos pertence ao agente que está operando a ferramenta.

A montagem vertical inclui a moldura Vice Sunset v3 com a logo, título no box aprovado e legendas Inter em uma linha. Os cortes internos e o zoom têm uma etapa assistida descrita no [guia de execução](docs/EXECUCAO_DA_MONTAGEM.md). A logo GTA VI é um arquivo de terceiro incluído no pacote local a pedido do usuário. Confirme a autorização aplicável antes de publicar o pacote com a logo.

## Publicação

Crie um repositório vazio na sua conta do GitHub e inicialize o Git na pasta deste pacote. Envie somente o conteúdo do pacote, com a licença que você escolher para o seu código. Preserve THIRD_PARTY_NOTICES.md. Revise o conteúdo e a visibilidade do repositório antes do primeiro push.

Na pasta extraída `cortes-clips`, depois de criar o repositório vazio e definir a licença, use:

```sh
git init -b main
git add .
git diff --cached --stat
git commit -m "Adiciona Cortes Clips"
git remote add origin https://github.com/SEU-USUARIO/cortes-clips.git
git push -u origin main
```

Substitua `SEU-USUARIO` pelo proprietário do repositório. Quem receber acesso pode clonar esse endereço e seguir a instalação acima.
