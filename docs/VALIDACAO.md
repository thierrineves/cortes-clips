# Validação local — 18 de novembro de 2026

- Ambiente Python 3.13.18; `doctor` confirma FFmpeg, ffprobe, Streamlink, yt-dlp e faster-whisper; `uv pip check` confirma compatibilidade das 42 dependências instaladas.
- `python -m unittest discover -s tests -v`: **32 testes passaram**, incluindo FFmpeg real, transcrição simulada com timestamps NumPy e decodificação real usada pelo Whisper.
- Transcrição **real** com Whisper small/CPU int8 de uma amostra sintética falada em português de 28,083 s: cinco segmentos, horários por palavra.
- Seleção editorial feita pelo Codex, não por regra local: trecho 2,600–23,250 s, preservando a conclusão da história e removendo a mudança de assunto. Plano em `examples/selection-demo.json`.
- Exportados horizontal 640 × 360 e vertical 720 × 1280 com áudio e legendas. ffprobe: 20,625 s de vídeo (arredondamento ao quadro); o intervalo solicitado é 20,650 s. Decodificação completa e quadros de amostra conferidos.
- Fontes sem áudio, caminhos com aspas/espaços, vídeos com um único quadro prolongado, planos inválidos, sobreposição, NaN e caminhos inseguros estão cobertos por testes.
- Captura independente validada com fonte local: buffer limitado, snapshot imutável, posição na origem, encerramento normal e encerramento abrupto do supervisor sem deixar FFmpeg gravando.
- Snapshot de dois segundos a 10 fps com áudio AAC: o corte preserva exatamente 20 quadros. O uso de microssegundos na busca evita que arredondamentos descartem um quadro na borda.
- Smoke por **runner da skill instalada**: start, status, snapshot de 3,000 s, review e stop; todos funcionaram e o estado final foi `stopped`, motivo `user`.
- Download/importação por URL validado por revisor com servidor HTTP local e yt-dlp real; nenhuma mídia de terceiros foi baixada nesse teste.
- Revisão independente encontrou falhas e elas receberam correções com regressões: diretório de chamada, validação de manifesto, timestamps, quadro prolongado, histórico de exportações, identificação temporal de snapshots e processos órfãos.
- Revisão independente final concluída: os 32 testes passaram também para o revisor; demonstrações decodificadas integralmente; nenhum achado importante ficou pendente.
- Skill `chat-clipper` instalada e validada, com cópia distribuída no projeto. Grafos Graphify foram gerados por AST local e não usaram uma API de IA.

## Limites desta validação

**Não foi testada uma transmissão Twitch real**, porque nenhum canal foi fornecido para a operação. Não foram exercitadas autenticação de sites, publicação em redes sociais nem horas de processamento contínuo. Conexões e reconexões dependem do serviço remoto. O alinhamento de chat é aproximado e amostrado. Os testes comprovam o fluxo local, não a qualidade editorial de qualquer live futura.
