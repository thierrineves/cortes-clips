# Montagem gamer — implementação e validação

18 de novembro de 2026. Referência original preservada em `assets/references/layout-usuario.png`.

## Requisitos persistidos

- Vertical9:16, 720×1280, câmera superior, título sobre a junção, gameplay inferior e legenda na região intermediária inferior sobre o jogo.
- Cores da referência são apenas marcadores; acabamento neutro e conteúdo real dos recortes da fonte.
- Gameplay horizontal com recorte centralizado `cover` preenchendo a área.
- Depois de apresentar todos os cortes, perguntar se algum deve mostrar a tela inteira; adaptar individualmente os indicados com `gameplay_fit: contain`, sem mudar o restante da montagem nem os outros cortes.
- Instruções sincronizadas no AGENTS.md do projeto, preferências globais do Codex, skill instalada e protocolo/prompt para outros assistentes.

## Implementação

`layouts/gamer-stack-v1.json` fixa a geometria de destino. `composition.json` define as regiões normalizadas da câmera e gameplay em cada fonte. `composition` na CLI configura essas regiões; sem perfil válido, vertical/both falha antes de criar exportações. Snapshots podem herdar perfil apenas se a identidade da captura corresponder. Mudança na proporção da fonte exige reconfiguração.

`chat_clipper/gamer.py` compõe as duas regiões, máscara arredondada, título e legendas. Título aparece durante todo o corte. As legendas com timestamps por palavra são agrupadas em até quatro palavras por bloco, sem excluir a fala. Textos são ajustados para as caixas fixas; títulos impossíveis são rejeitados para reescrita. Sintaxe ASS encontrada na fonte é escapada.

Cada exportação preserva perfil e preset usados. O manifesto guarda o ajuste efetivo da gameplay de cada corte, permitindo adaptações sem reescrever o perfil padrão nem alterar arquivos anteriores. Horizontal continua sendo uma cópia técnica opcional na proporção original.

## Evidências

- **50 testes passaram**, execução completa em `layout-testes-final.log`.
- Testes FFmpeg medem pixels: a câmera vem da região vermelha e a gameplay da região azul em fonte de teste; pixels de título e legenda ficam dentro das caixas definidas. Bordas externas e arredondamento também são conferidos.
- Outro teste usa gameplay horizontal com faixas laterais verdes e centro azul: `cover` centralizado mostra o centro; a adaptação individual `contain` mostra as duas laterais. O primeiro manifesto e seu perfil permanecem intactos.
- Cobertura para ausência de perfil, NaN/bool, região inválida, mudança de proporção, identidade da captura, fonte sem áudio, título grande demais, escape ASS, vídeo com quadro prolongado e caminhos com espaços/aspas.
- Testes anteriores de captura, decoder Whisper e persistência de sessões continuam passando.
- Demonstração em `examples/gamer-stack/demonstracao.mp4`: vídeo720×1280, 20,667s, áudio presente. Usa câmera e jogo **simulados**, com o áudio português da amostra anterior; não representa teste de uma webcam ou live reais.
- Prévia extraída do vídeo em `examples/gamer-stack/previa.png`, examinada visualmente pelo agente principal.
- Graphify atualizado por AST local:157 elementos,474 relações,11 grupos; sem chamada a API paga para extração.

## Revisão e limites

A revisão final do código/render desta alteração foi feita pelo próprio agente principal. A revisão delegada conferiu inicialmente o diagrama e a documentação; os subagentes ficaram indisponíveis por limite de uso antes de concluir a revisão da renderização. Não apresentar isso como uma revisão independente completa.

O enquadramento de uma fonte real ainda depende de inspeção de seus frames e configuração correta das regiões. Não há detecção facial automática. Os cortes antigos foram preservados como histórico e não foram convertidos silenciosamente para este padrão.
