# Patches — as correções propostas

Três patches de **mudança mínima** para os defeitos D01, D02 e D03. O guia do aluno §4 é explícito:

> *Corrigir é opcional e vale ponto — mas só se vier acompanhado do teste que falhava antes da
> correção. Se for corrigir, faça em um patch/branch separado e explique no relatório.
> **A ordem importa: primeiro o teste que falha, depois a correção que o faz passar.***

**A ordem foi respeitada.** Os três testes existem desde os HANDOFFs 02 e 03, com o vermelho colado
em [`../docs/mapa-defeitos.md`](../docs/mapa-defeitos.md) **antes** de qualquer correção ser
escrita. Estes patches são posteriores.

## Eles não editam o pacote sob teste na entrega

Esta é a regra de ouro do enunciado, e o desenho a preserva: os patches vivem **aqui**, como
arquivos de texto, e são aplicados ao **clone dentro do container** (`/opt/sentinela`), que é
descartado quando o container morre. O nosso repositório nunca contém o pacote `sentinela`:

```bash
git ls-files | grep -c '^src/sentinela/'    # 0
```

## Os três

| Patch | Defeito | O que muda |
|---|---|---|
| `D01-vazamento-temporal.patch` | **D01** | remove `center=True` de `temp_media_6h`. **Não** toca `min_periods=1` — mexer nele introduziria NaN nas primeiras linhas e `Modelo._matriz` levantaria `ValueError` por não-finitude |
| `D02-vazamento-alvo.patch` | **D02** | remove o ramo de `_risco_por_maquina` que recalcula o risco a partir de `falha_72h`. A tabela congelada passa a ser sempre a fonte |
| `D03-unidade-de-pressao.patch` | **D03**, e absorve **D19** | converte psi → bar em `limpar` usando `FATOR_PSI_POR_BAR = 14.5038`, e **rejeita** unidade fora do domínio com `ValueError` nomeando a coluna |

## Como aplicar

Não aplique à mão. O alvo faz tudo, dentro do container:

```bash
make correcoes
```

Ele aplica os três, re-roda `-m defeito` e imprime a tabela de métricas antes/depois por versão. O
log fica em [`../evidencias/log-correcoes.txt`](../evidencias/log-correcoes.txt).

Para só conferir que aplicam, sem aplicar:

```bash
docker compose run --rm suite git -C /opt/sentinela apply --check /trabalho/patches/*.patch
```

## O que esperar: as métricas vão CAIR

E isso **não é falha da correção — é o achado**.

Os artefatos de modelo (`modelo_v1.json`, `modelo_v2.json`) foram **treinados com os defeitos
presentes**. A floresta aprendeu a usar `maquina_risco` inflada pelo rótulo e a pressão em duas
escalas misturadas. Corrigir a entrada sem retreinar entrega ao modelo uma distribuição que ele
nunca viu.

É o parágrafo de conclusão do [`../relatorio.md`](../relatorio.md):

> **Corrigir o código exige retreinar o modelo. E retreinar exige, antes, esta suíte** — porque sem
> ela não há como saber se o modelo novo é melhor que o velho.

## Por que os outros 21 defeitos não têm patch

| Motivo | Defeitos |
|---|---|
| Exige **retreinar** ou mudar a forma da entrada do modelo (`ORDEM_FEATURES`), o que `modelo.carregar` valida | **D06**, **D14**, **D24** |
| Exige alterar `artefatos/` dentro do pacote sob teste, violando a regra de ouro | **D23** |
| Fora do escopo de "mudança mínima": exigiriam redesenhar `limpar`/`construir` | os demais |

Todos os 24 estão documentados com teste que falha, número medido, causa raiz e impacto na planta —
que é o que o enunciado pede. Corrigir é o bônus.
