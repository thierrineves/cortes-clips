# Executar o plano do editor

O Sol entrega a ficha de curadoria e os intervalos exatos, a ordem de reprodução, o título, os recortes dos painéis e as marcações de zoom. Um executor que receba esse plano pode montar e conferir a edição sem reavaliar a live.

- Para um trecho contínuo, use `./run.sh render SESSAO --plan selection.json`. A exportação vertical aplica a moldura Vice Sunset v3 com a logo aprovada, o título na divisória e a legenda Inter em uma linha. Revise a transcrição para separar a fala do streamer dos diálogos do jogo.
- Para cortes internos, registre o início e o fim de cada trecho na fonte e sua posição na timeline. Para antecipar uma reação, coloque seu intervalo primeiro e depois retome a preparação. Use FFmpeg ou um editor de vídeo para extrair e concatenar os trechos na ordem indicada. Normalize resolução, FPS e áudio antes da concatenação, preservando o sincronismo. Importe a mídia montada como nova sessão, configure os recortes e use tempos relativos à nova mídia. Refaça a transcrição ou remapeie os tempos das palavras para a timeline montada.
- Para zoom, o plano indica painel, início, fim, escala e ponto de atenção. Aplique o zoom somente à mídia recortada daquele painel antes de recompor o quadro. Preserve a dimensão do painel, a divisória, a logo e as legendas. Se a montagem já estiver composta, faça o ajuste em um editor com máscaras independentes para câmera e jogo.
- Confira o resultado nos pontos de junção e de zoom. Valide a ordem dos acontecimentos, a sincronização, a duração e a legibilidade das legendas no celular.

O CLI automatiza a versão contínua. Cortes internos e zoom são instruções para uma etapa assistida de montagem. Registre no resultado qualquer ajuste planejado que não foi aplicado.
