# Padrão obrigatório de montagem

Definido pelo usuário em 18 de novembro de 2026 a partir de `assets/references/layout-usuario.png`. As cores rosa, azul e verde do desenho **são apenas marcadores de posição**, conforme confirmação do usuário. Não devem ser pintadas sobre o vídeo final.

## Composição

Formato vertical **9:16**, exportado em 720×1280. A expressão verbal “vertical 16 por 9” foi interpretada pela referência visual: largura menor que altura.

1. **Câmera do jogador:** ocupa a parte superior. Deve vir do recorte real da câmera na fonte, não de uma cópia arbitrária da gameplay.
2. **Título do corte:** faixa central na transição abaixo da câmera, parcialmente sobreposta à junção. O texto vem de `clip.title` no plano editorial.
3. **Gameplay:** área principal abaixo da câmera. A imagem do jogo é recortada da região correspondente da fonte.
4. **Legenda da fala:** sobre a gameplay, na região inferior intermediária indicada em verde no desenho, sem ir para o rodapé.

Os destinos são fixos no preset `layouts/gamer-stack-v1.json`:

| Região | X | Y | Largura | Altura |
|---|---:|---:|---:|---:|
| Painel interno | 40 | 32 | 640 | 1212 |
| Câmera | 40 | 32 | 640 | 420 |
| Gameplay | 40 | 452 | 640 | 792 |
| Card do título | 144 | 389 | 424 | 110 |
| Região da legenda | 180 | 928 | 360 | 72 |

Posições em pixels no quadro720×1280, adaptadas proporcionalmente do desenho. Moldura Vice Sunset v3 com logo, título Bowlby One SC em caixa alta e legenda Inter branca em uma linha. O painel conserva as bordas arredondadas da referência. Não substituir por imagem inteira no centro com fundo desfocado.

## Enquadrar a fonte

A posição da câmera dentro de uma transmissão varia. Antes da primeira renderização, a IA deve examinar os frames e configurar `composition.json` na sessão, usando coordenadas normalizadas. Não existe detecção facial automática nessa implementação.

```sh
./run.sh composition "/caminho/sessao" \
  --camera "0,0,0.30,0.30" \
  --gameplay "0.30,0.30,0.70,0.70" \
  --gameplay-fit cover
```

**Os números acima são somente um exemplo de sintaxe**, não coordenadas para aplicar a qualquer live. Cada região usa `x,y,width,height` relativos à imagem inteira, entre0 e1. Nenhuma pode ultrapassar os limites. Câmera e gameplay não podem ser o mesmo recorte.

A câmera preenche sua área pelo recorte configurado. **O usuário definiu que todos os jogos são horizontais e que o padrão é `cover`, preenchendo toda a área com recorte sempre centralizado.** Não criar faixas para mostrar o jogo inteiro antes de entregar a primeira versão.

**Depois de apresentar todos os cortes, perguntar:** “Há algum corte que você quer adaptar para mostrar a tela inteira do jogo?” Não interromper a montagem para perguntar isso antes de mostrar o resultado, nem perguntar separadamente após cada corte.

Se o usuário indicar um corte, salvar um novo plano com `"gameplay_fit": "contain"` somente nesse item. `contain` mostra a região inteira do jogo, centralizada na mesma área, podendo deixar faixas neutras. Câmera, título e legenda continuam nas posições do modelo. Os demais cortes e o perfil padrão permanecem `cover`.

```json
{
  "id": "historia-01",
  "title": "Título do corte",
  "start": 12.5,
  "end": 44.8,
  "reason": "Adaptação solicitada após a primeira entrega.",
  "format": "vertical",
  "gameplay_fit": "contain"
}
```

Para uma captura live, o perfil pode ser salvo na sessão de captura após a IA inspecionar um snapshot. Os snapshots dessa captura podem herdar o perfil ao renderizar, conferindo a identidade da captura. Um perfil salvo diretamente no snapshot tem precedência. Uma fonte com proporção diferente precisa de novo enquadramento.

## Execução e auditoria

- Entrega padrão: `format: "vertical"`. `horizontal` é apenas uma cópia técnica na proporção original quando pedida; não é o corte montado deste padrão. `both` acrescenta essa cópia técnica à montagem vertical.
- Sem perfil válido, a renderização vertical falha com instrução para configurar. Não inventar câmera nem voltar à montagem antiga.
- Se não existir câmera na fonte, informar essa condição e pedir ao usuário como tratar a exceção antes de gerar uma montagem diferente do padrão.
- A legenda é derivada da fala; em uma fonte sem fala a região fica livre, sem texto inventado. O título continua presente durante todo o corte.
- Cada exportação mantém a configuração de composição e o preset efetivamente usados, além do manifesto editorial. Alterações futuras no perfil não mudam arquivos já gerados.

Os vídeos anteriores à definição deste padrão foram preservados como histórico. Eles não são exemplos do padrão atual. A demonstração atual será identificada em `examples/` com nome `gamer-stack`.


