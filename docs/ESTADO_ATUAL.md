# Estado atual da ferramenta

## Implementado

- CLI Python local com sessões persistentes, importação de arquivo ou URL, captura Twitch, buffer limitado, snapshots, transcrição, material de revisão e renderização.
- Whisper small local para transcrição com horários por palavra; CPU/int8 no Mac. Sem transcrição externa por API.
- A seleção é feita pelo assistente de IA ativo, a partir da transcrição e de frames. Contrato público em `docs/FLUXO_PARA_IA.md`.
- Montagem vertical padrão720×1280 com câmera do jogador no topo, título na junção, gameplay abaixo e legenda em posição fixa, conforme `PADRAO_MONTAGEM.md`. Exige perfil de regiões da fonte em `composition.json`; não usa mais a versão vertical de fundo desfocado. Exportação na proporção original segue disponível apenas como cópia técnica opcional. SRT/ASS e manifesto editorial permanente a cada exportação.
- Captura independente com limite de tempo, tentativas de reconexão, proteção de disco e encerramento dos subprocessos se o supervisor morrer.
- Protocolo neutro para assistentes e integração instalada para o Codex neste computador.

Consulte INSTALACAO.md para os limites da distribuição.
