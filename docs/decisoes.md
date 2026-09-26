# Decisões de execução

O que o SPEC e os HANDOFFs **não** dizem, e que custou tempo descobrir. Convenções que já estão
valendo no código — segui-las é mais barato que redescobri-las.

Previsto em SPEC §8 ("fica para a execução decidir, registrando em `docs/decisoes.md`").
Origem: execução dos HANDOFFs 01 e 02, 20260924.

## Fixtures do `conftest.py`

Escopo de função salvo onde indicado.

| Fixture | Escopo | Devolve | Use quando |
|---|---|---|---|
| `ambiente` | sessão | `{sha, ref_esperado, versao_sentinela, versoes}` | precisa do SHA do SUT ou das versões em runtime |
| `semente` | função | `int` de `SUITE_SEED` (default 42) | precisa do número da semente |
| `gerador` | função | `np.random.default_rng(semente)` | **sempre que sortear**; nunca crie um RNG na mão |
| `n_boot` | função | `int` de `SUITE_N_BOOT` (1000; 2000 no alvo `evidencias`) | bootstrap |
| `_lote_treino` `_lote_teste` `_lote_producao` | sessão | `DataFrame` cru, compartilhado | **nunca injete num teste** — veja abaixo |
| `lote_treino` `lote_teste` `lote_producao` | função | `.copy()` do lote de sessão | qualquer teste que toque no quadro |
| `predicoes` | sessão | fábrica `(conjunto, versao="v1", limiar=0.5) -> (y, proba, predicao)` | comparar versões, medir métricas |
| `modelo_cache_frio` | função | `modelo._CACHE` vazio, restaurado depois | o raro teste que observa a primeira carga |
| `medicoes` | função | o dicionário de `medicoes.json` | gravar um número medido |
| `_isola_estado_global` | função, **autouse** | — | nada a fazer: já roda em todo teste |

Regras que o código assume:

- **`_lote_x` é privado por contrato, não por acidente.** O underscore marca "de sessão,
  compartilhado, não copie referência para dentro de um teste". Metade dos testes adversariais muta
  o quadro; injetar `_lote_teste` direto contamina todos os testes seguintes com uma falha fantasma
  difícil de rastrear. Injete sempre `lote_teste`.
- **`gerador` é novo a cada teste**, derivado da mesma `SUITE_SEED`. É o que torna a ordem dos
  testes irrelevante para o resultado. Não guarde um RNG em variável de módulo.
- **`predicoes` é memoizada e devolve o mesmo objeto** a cada chamada com a mesma chave. Se for
  mutar o array, copie. Ela existe porque a floresta sobre 4.200 linhas × dezenas de testes não cabe
  no orçamento de tempo (SPEC D6).
- **`medicoes` é o dicionário de módulo `_MEDICOES`, compartilhado pela sessão inteira.** As chaves
  do esquema de C8 (`sut`, `linha_de_base`, `v1_v2`, `limiar`, `flip`, `contrafactual`, `drift`,
  `sensibilidade`) já
  nascem criadas: preencha-as, não as substitua. É despejado em `pytest_sessionfinish`.
- **Nada de relógio, duração ou caminho absoluto em `medicoes.json`.** O arquivo é comparado byte a
  byte entre duas rodadas com a mesma semente (S13). Qualquer valor não determinístico quebra a
  prova. É escrito com `sort_keys=True`.
- **`_isola_estado_global` zera `features._RISCO_CONGELADO`, mas só *vigia* `modelo._CACHE`.**
  Limpar o cache custaria reparsear ~550 KB de JSON por teste. A fixture falha se um teste
  **substituir** um modelo já carregado. Precisa do cache vazio? Use `modelo_cache_frio`.

## O par de testes do D23

Padrão a repetir sempre que o defeito for um **estado de fábrica** do SUT, e não um comportamento
que a suíte provoca:

- **Teste 1 — a invariante, com `xfail(strict=True)`.** Asserta o que *deveria* valer
  (`verificar_manifest() == []`), carrega `@pytest.mark.defeito` e um `reason` que começa com
  `D<nn> — ` (contrato C5). Fica vermelho no `make defeitos`, verde-como-XFAIL no `make suite`.
- **Teste 2 — o guarda, verde.** Asserta que o estrago é **exatamente** o catalogado
  (`set(verificar_manifest()) == DIVERGENCIAS_CONHECIDAS`).

Por que os dois: o `xfail` sozinho é cego a agravamento. Se o SUT ganhar uma quinta divergência, o
teste 1 continua falhando do mesmo jeito e ninguém percebe. O teste 2 é quem grita. E se o defeito
for corrigido, `xfail_strict` transforma o teste 1 em XPASS e derruba a suíte — o alarme de que a
especificação do defeito ficou obsoleta (S10).

`DIVERGENCIAS_CONHECIDAS` mora em `scripts/smoke.py`, **não** no teste: o smoke do build e o teste
precisam da mesma lista, e duplicá-la garante que um dia divirjam. Os testes importam com
`from scripts.smoke import DIVERGENCIAS_CONHECIDAS` — funciona porque a rootdir do pytest
(`/trabalho`) entra no `sys.path` e `scripts/` é um namespace package (não tem, nem precisa de,
`__init__.py`).

## `--strict-markers`: a validação óbvia não prova nada

`pytest -m marker_inexistente` **não** falha. Ele desseleciona tudo e sai 5 ("no tests collected").
`--strict-markers` valida markers **aplicados a testes** via `@pytest.mark.x`, não as expressões
passadas em `-m`.

A prova que funciona é um teste temporário com um marker não registrado:

```
'marker_que_nao_existe' not found in `markers` configuration option    # exit 2
```

O HANDOFF 01 trazia a versão errada; foi corrigido lá. Se aparecer de novo em outro HANDOFF, é o
mesmo engano.

## Por que `bash -o pipefail -c '... | tee ...'` dentro do container

Os alvos `suite` e `defeitos` do Makefile geram os logs de C7 **dentro** do container, não com um
`tee` do lado do host. Três motivos, nessa ordem:

1. **O `tee` do host tornaria o teste de uid circular.** `evidencias/log-suite.txt` nasceria com o
   uid do host por construção, e S7 — que existe para provar que o *container* escreve com o uid
   certo — passaria mesmo com a imagem construída com o uid errado. Escrevendo lá dentro,
   `stat -c '%u:%g'` devolvendo `1001:1001` é uma prova de verdade.
2. **`pipefail` preserva o exit code do pytest.** Sem ele o alvo herda o código do `tee`, que é
   sempre 0, e `make suite` ficaria verde com a suíte vermelha.
3. **`bash`, não `sh`.** `-o pipefail` não existe no `sh` do Debian. A imagem tem bash.

O alvo `defeitos` leva um `-` na frente da receita: ele **deve** sair 1 (é o log vermelho da
entrega, S5) e sem o `-` o make abortaria com esse 1 esperado.

## Miudezas que custam meia hora

- **`export UID=$(id -u)` não funciona no bash** — `UID` é readonly. O Makefile faz
  `export UID := $(shell id -u)`, que funciona porque é o make exportando, não o shell. À mão, use
  `env UID=$(id -u) GID=$(id -g) docker compose ...`.
- **Os caminhos de junitxml ficam por alvo no Makefile, fora do `addopts`.** Se entrarem no
  `addopts`, `make defeitos` sobrescreve o `junit-suite.xml` do `make suite`.
- **`ARGS` do Makefile entra dentro de aspas simples** no `bash -c`. `ARGS="-k foo"` funciona;
  `ARGS` contendo aspas simples, não.
- **Um único escritor por diretório de trabalho.** A etapa 01 foi trabalhada em dois terminais em
  paralelo no mesmo diretório e um sobrescreveu os arquivos do outro. Antes de começar, um
  `git status` e um olhar nos mtimes.
- **O host do laboratório é arm64** (`aarch64`), uid/gid 1001. A imagem é construída para a
  arquitetura local; a banca em x86 vai reconstruir, não reusar um `docker save` daqui.


## Escrever teste de defeito sem escrever teste inútil

A regra de processo (HANDOFF 02 em diante) é: escrever **sem** o marker, rodar, ver o
vermelho, colar em `docs/mapa-defeitos.md`, e só então aplicar `defeito` + `xfail`. Ela
existe porque **três dos oito oráculos do Bloco A passaram na primeira tentativa** — e um
teste de defeito que passa é pior que teste nenhum: dá a impressão de que a costura foi
verificada.

Os três, e o que estava errado:

- **D07, `prever_registro`** — comparava a decisão de **uma linha**. As duas decisões
  coincidem em ~46 % dos casos. Varrendo o lote: 39 de 72 leituras (54,2 %) mudam.
  → Quando o defeito é probabilístico, o oráculo varre o lote e **reporta a taxa**.
- **D09, estabilidade do recorte** — recortava **por motor**. Não expõe nada: as janelas já
  são por motor e `maquina_risco` é calculada dentro do próprio motor. Com recorte
  **temporal** (como a planta reprocessa de verdade), 7 das 13 features mudam.
  → O recorte do teste tem de ser o recorte que a operação faz.
- **D22, rastreabilidade** — não descartava nenhuma linha, então o índice reconstruído
  coincidia com o original por acidente.
  → Se o defeito só aparece sob uma condição, o teste **cria** a condição.

## O conjunto de teste é o único limpo — insumo do HANDOFF 03

Não é detalhe de marcação: é o achado mais forte do Bloco A. Linhas fora da faixa da ficha
técnica existem em **treino** e em **produção**, e **zero** no conjunto de teste:

| conjunto | linhas | rpm fora de faixa | pressão convertida fora de faixa |
|---|---:|---:|---:|
| treino | 16.800 | 4 | 5 |
| teste | 4.200 | **0** | **0** |
| producao | 4.200 | 1 | 1 |

O conjunto de teste é exatamente onde a Nortemec mediu os **+3,5 pp** que justificam promover a
v2. Quem só olha a métrica de teste — que foi o que aconteceu — nunca vê a violação: ela está
no dado com que o modelo foi treinado e volta no dado que ele vê em produção.

Consequências a carregar adiante:

- **HANDOFF 03 (linha de base):** a linha de base honesta não pode ser lida só no conjunto de
  teste. Os três conjuntos entram na tabela, e a diferença entre eles é resultado, não ruído.
- **HANDOFF 04 (drift):** treino e produção compartilham uma anomalia que o teste não tem. Isso
  muda a leitura de qualquer detector de drift teste × produção.
- **Relatório (HANDOFF 06):** vale parágrafo próprio. É o caso concreto de "a métrica de teste
  não descreve o sistema", que é a tese da entrega.

Detalhe correlato do D23: `risco_maquina.json` **é** consistente com o `treino.csv` publicado —
os 25 valores são exatamente `round(média_por_motor, 6)`, a precisão de gravação do arquivo. Dados
e tabela de risco foram regerados juntos; os **modelos** é que não acompanharam (ainda batem com o
manifest antigo). Então o caminho sem vazamento, que cai na tabela congelada, está sadio — e o que
falta de procedência são os artefatos de modelo. Ver o gate da Etapa 3 do HANDOFF 03.

> **Armadilha:** comparar essa tabela com `==` dá "2 de 25" e inverte a conclusão. São floats de
> precisão plena contra decimais arredondados a 6 casas; os 2 que "batem" são os dois zeros
> exatos. Use tolerância de 1e-6 — ou compare contra `round(x, 6)`, que é o teste decisivo.

## `xfail` por parâmetro quando o defeito não está em todo lugar

D17 (faixas da ficha) está em `treino` e `producao` e **não** em `teste`. `xfail(strict=True)`
na função inteira viraria XPASS em `teste` e derrubaria a suíte. A marca vai no
`pytest.param`:

```python
pytest.param(nome, marks=[pytest.mark.defeito,
                          pytest.mark.xfail(strict=True, reason="D17 — …")])
```

Vale para qualquer defeito que dependa do conjunto, da versão do modelo ou do lote.

## Convenções dos módulos de `suite/`

- **`ficha.py` é declarativo.** Faixa, unidade e ruído vêm do README do SUT e viram dado.
  Nenhum número da ficha aparece solto num `assert` de teste. Mudou a ficha? Uma linha.
- **Validador levanta `ValueError` nomeando a coluna e devolve `True`** (padrão da aula 3).
  O `is True` no teste não é decoração: garante que "não levantou" foi resultado, não
  silêncio acidental.
- **`fabrica.py` nunca usa o relógio nem o RNG global.** Toda função recebe `seed`. Dois
  lotes com a mesma semente são idênticos — há teste `meta` para isso.
- **Os lotes da fábrica nascem válidos**, dentro da ficha. Assim, qualquer violação que um
  teste observe é a que o próprio teste injetou.

## Aresta do par de versões pinado

`pd.Timedelta("24h")` dispara `DeprecationWarning` de unidade genérica em
**numpy 2.5.3 + pandas 2.3.3**. Use `np.timedelta64(24, "h")`. Como `filterwarnings` só
promove `FutureWarning` a erro, isso passa silencioso — mas vira erro numa numpy futura.


## Laço por etapa, e o fechamento

**Regra permanente (20260924).** A documentação acompanha a execução **etapa a etapa** — não se
escreve tudo no fim. `status: concluido` é o **último** ato, nunca o primeiro.

### Por que etapa a etapa

É preciso poder retomar o projeto **a qualquer momento**, inclusive no meio de uma etapa.
Documentação escrita só no fim faz o documento mentir quando há interrupção: ele diz
que a Etapa 3 está pendente quando ela já rodou, e quem chega depois refaz ou pula trabalho.

Isto já era o método, e passou batido nos HANDOFFs 01 e 02: o `## Registro de execução` do próprio
template manda "atualize a seção deste HANDOFF no STATUS consolidado **a cada etapa**", e
`ai/operacao/guias/05-executar-handoff.md` (Passos 1) descreve o laço como executar → conferir
*Done quando* + *Validação* → atualizar. O acréscimo é que **o documento do HANDOFF também
acompanha**, não só o STATUS.

### O laço

Por etapa, na ordem:

1. Executa a etapa.
2. Roda o campo `**Validação:**` **de verdade** e guarda a saída.
3. **No HANDOFF:** marca o estado da etapa e anota o que de fato aconteceu. Desvio entra na tabela
   do `## Registro de execução` **na hora**, não no fim.
4. **No STATUS:** atualiza a linha daquela etapa em `## Detalhamento` — status, data, nota curta.
5. Se a etapa fecha um `V<n>`, registra a saída **real** em `## Evidências` do STATUS **naquele
   momento**. É justamente a saída que se perde se ficar para depois.
6. Só então passa para a etapa seguinte.

### Critério de aceite da regra

A qualquer instante, se o trabalho for interrompido, quem retomar lendo **apenas** o plano, o
status e este arquivo tem de saber: em que etapa o projeto parou, o que já foi validado e com qual
saída, e o que falta. **Se for preciso lembrar de algo que não está escrito, a regra não foi
cumprida.**

### Checklist de fechamento

Conferência **final** — não é o momento em que a escrita acontece. Se o checklist encontrar muita
coisa por escrever, é sinal de que o laço por etapa não foi seguido.

A regra nasceu de um atrito real: nos HANDOFFs 01 e 02 o trabalho técnico estava certo e a
evidência estava no STATUS, mas os documentos se declaravam `concluido` com caixas vazias,
`## Registro de execução` só com o texto do template, contagens defasadas, uma referência a uma
premissa inexistente (`P12`) e dois campos de `Validação` que nunca tinham sido rodados. Foi
preciso cobrar em duas rodadas.

A regra nasceu de um atrito real: nos HANDOFFs 01 e 02 o trabalho técnico estava certo e a
evidência estava no STATUS, mas os documentos se declaravam `concluido` com caixas vazias,
`## Registro de execução` só com o texto do template, contagens defasadas, uma referência a uma
premissa inexistente (`P12`) e dois campos de `Validação` que nunca tinham sido rodados. Foi
preciso cobrar em duas rodadas.

Conferir isto **antes** de escrever `status: concluido`:

1. **Todo campo `**Validação:**` de cada etapa foi de fato EXECUTADO**, e a saída registrada.
   Campo escrito e não rodado não conta. Foi exercitar o S2 — declarado coberto desde o início,
   nunca rodado — que revelou que o `git clone` do `Dockerfile` não estava sendo checado. Se um
   campo não fizer sentido executar, **diga isso explicitamente**; não deixe em silêncio.
2. **Zero `- [ ]` restantes**, em pré-requisitos e em `## Validação final`. Resultado parcial vira
   `- [x] V<n> — parcial: <o que falta> (fecha no HANDOFF <n>)`, nunca um check limpo. Um `[x]`
   limpo sobre resultado parcial é pior que a caixa vazia.
3. **`## Registro de execução` preenchido:** data, executor, resultado com números, ponteiro para a
   evidência, e a tabela de desvios com a coluna "onde ficou".
4. **Contagens conferidas contra o disco** — testes, funções, ids, validadores, commit. Três vezes
   uma contagem derivou por ser reescrita de memória. Conte com `grep -c` e `--collect-only`.
5. **Referências cruzadas conferidas:** todo `P<n>`, `C<n>`, `S<n>`, `D<n>` citado existe no SPEC;
   todo `R<n>`/`AC<n>` existe no PRD. O `P12` da Etapa 1 do HANDOFF 01 não existia — o SPEC §2 vai
   de P1 a P10.
6. **STATUS atualizado:** tabela de etapas, `## Evidências` com a saída **real** de cada `V<n>`
   (nunca paráfrase), `## Histórico`, `## Bloqueios` se houver. E o PROJETO em `ai/projetos/`
   sincronizado.
7. **Divergência HANDOFF × SPEC:** o SPEC vence e o HANDOFF é corrigido, com o desvio registrado.
   Se for o SPEC que precisa crescer — como na cota do `test_suite_interna.py`, que subiu de 5 para
   10 funções e levou o total de 113 para 118 —, corrija o SPEC **e** os totais. Nunca resolva em
   silêncio.

Vale do HANDOFF 03 em diante. Os HANDOFFs 01 e 02 foram trazidos a essa forma retroativamente.


## Os modelos são coerentes com os dados publicados (medido, não conjecturado)

**Medido em 20260924**, antes do HANDOFF 03, por leitura pura dos JSON — não roda nada.

A pergunta: os artefatos de modelo foram treinados sobre a geração dos dados que está no
repositório hoje, ou sobre a anterior (a que o `manifest.json` descreve)? Ela importa porque, se
fossem obsoletos, o gate dos +3,5 pp da Etapa 3 do HANDOFF 03 mediria outra coisa.

**O método.** Uma floresta do scikit-learn põe o corte no **ponto médio entre dois valores
observados** da feature. Então os limiares dos nós que testam `maquina_risco` (índice 10 de
`ORDEM_FEATURES`) são uma impressão digital do conjunto de valores usado no treino. Basta
compará-los com os pontos médios de todos os pares dos valores de hoje.

**O resultado.**

| | v1 | v2 |
|---|---:|---:|
| nós internos | 4.176 | 12.174 |
| nós que testam `maquina_risco` | 400 (9,6 %) | 860 (7,1 %) |
| limiares fora da faixa atual | **0** | **0** |
| casam com um ponto médio dos valores atuais (tol. 1e-6) | **400 / 400** | **860 / 860** |
| distância máxima | 4,76e-07 | 4,76e-07 |

**A forma exata do resultado, melhor que qualquer tolerância.** `scripts/treinar.py` linha 58
grava `"limiar": [... round(float(v), 6) ...]`. Então o limiar publicado é, por construção,
`round(ponto_médio_em_precisão_plena, 6)`. E é isso que se mede:

```
limiares IDÊNTICOS a round(ponto_medio_pleno, 6):  v1 400/400   v2 860/860
```

**Bit a bit, não dentro de tolerância.** As distâncias abaixo são consequência, não o achado:

| referência | v1 | v2 | por quê |
|---|---|---|---|
| ponto médio dos valores **plenos** | 4,761905e-07 | 4,761905e-07 | abaixo do teto teórico de 5e-07 do `round(.,6)` |
| ponto médio dos valores da **tabela** | 5,000000e-07 | 5,000000e-07 | média de dois decimais de 6 casas pode terminar em `…5` na 7ª |

Os dois números aparecem na literatura deste projeto e é fácil confundi-los: **5,000e-07 exato**
é contra os pontos médios da tabela arredondada, não o teto teórico sendo atingido. Contra os
valores plenos — que é a comparação que responde "de onde veio este corte" — o máximo fica
**abaixo** do teto, em 4,76e-07.

Não é acaso, e com igualdade exata dá para calcular direito. Há 12 valores distintos:
C(12,2) = 66 pares, que colapsam em **62** pontos médios distintos em precisão plena — e, depois
do `round(.,6)` da linha 58, em **61** alvos exatos. O limiar é um decimal de 6 casas na faixa
[0, 0,214286], onde cabem ~214.286 valores possíveis. Acertar um dos 61 por acaso: **2,85e-04**
por limiar. Casar **1.260 de 1.260** é impossível por sorte.

*(64 é o número de pontos médios distintos da tabela **arredondada** — outra referência, fácil de
trocar por 62. O alvo da igualdade exata é 61.)*

**A conclusão, que corrige a anterior.** Eu havia escrito que "os modelos publicados não têm
vínculo de procedência com os dados publicados". A medição diz o contrário: os cortes de
`maquina_risco` **só poderiam ter sido aprendidos sobre exatamente estes valores**. Dados, tabela
de risco e modelos formam um conjunto coerente. O que mudou nos CSVs, entre o manifest e hoje, não
alterou a taxa de falha por motor.

**O que D23 é, então:** defeito de *bookkeeping* e procedência — o `manifest.json` não foi
regravado depois de os arquivos de dados serem reescritos —, e **não** evidência de artefato
obsoleto. Para o HANDOFF 03 isso é bom: o gate dos +3,5 pp começa sem uma explicação alternativa
pendurada. Se eles **não** reproduzirem, a causa terá de ser procurada em outro lugar, e a
hipótese "modelo obsoleto" já está descartada neste eixo.

**Ponta solta, barata de verificar no HANDOFF 04.** A v2 tem **2** limiares a menos de 5e-7 de um
valor da tabela congelada. O treino usa `maquina_risco` em precisão plena e o serviço sem rótulo
usa a tabela **arredondada a 6 casas**. O descasamento no valor da feature é menor que 1e-6 e só
é capaz de mudar decisão nesses 2 nós — magnitude conhecida e pequena, mas **mensurável**, e medir
em vez de estimar é o que o Bloco C cobra.

## D02: a intenção morta no `treinar.py` — insumo de causa raiz para o HANDOFF 03

`scripts/treinar.py`, linhas 72 a 79, literalmente:

```python
risco = limpo.groupby("id_maquina")["falha_72h"].mean().round(6).to_dict()
# … grava artefatos/risco_maquina.json …
features._RISCO_CONGELADO = None  # força releitura

X = features.construir(limpo)
```

A linha do `_RISCO_CONGELADO = None` existe com um único propósito: forçar a releitura da tabela
congelada que acabou de ser escrita. **E a linha seguinte a torna inútil** — `limpo` ainda tem a
coluna `falha_72h`, então `_risco_por_maquina` cai no ramo do recálculo por lote e a tabela
congelada **nunca é lida** no treino.

É intenção morta no código do próprio autor: alguém escreveu uma linha cujo único propósito é usar
o caminho congelado, e o caminho por onde o código passa ignora essa tabela. **É a melhor evidência
disponível de que D02 é acidente, e não decisão de design** — vale mais que qualquer inferência
nossa, e as três linhas devem ser citadas literalmente na seção de causa raiz do D02 no relatório.

Corolário já usado acima: por isso o treino usou `maquina_risco` em precisão plena, enquanto o
serviço sem rótulo usa a tabela arredondada.

**Honestidade:** a medição entrou como hipótese, com a ressalva de que podia não dar em nada. Deu
no contrário do que se supunha, que é exatamente o motivo de medir em vez de escrever "provável".


## Decisões que o SPEC §8 deixou abertas e o HANDOFF 03 fechou

**`test_pr_auc_da_v2_nao_e_pior_que_a_da_v1` é verde ou D11?** O SPEC fixou o teste e a métrica,
não o veredito, porque dependia da medição desta fase. Medido em `evidencias/linha-de-base.md`:

| conjunto | modo | PR-AUC v1 | PR-AUC v2 | v2 é pior? |
|---|---|---:|---:|---|
| teste | com vazamento | 0,8679 | 0,8117 | **sim** |
| teste | sem vazamento | 0,5811 | 0,6718 | não |
| producao | com vazamento | 0,7728 | 0,7198 | **sim** |
| producao | sem vazamento | 0,6433 | 0,6379 | **sim** |

**Veredito: é D11**, e o teste nasce `xfail` no HANDOFF 04. A v2 tem PR-AUC pior em três das
quatro leituras, e a única em que ganha é a que ninguém deveria usar para decidir (teste **com**
vazamento é o modo em que a métrica foi inflada). Na leitura que vale — sem vazamento, em
produção — a v2 é pior por 0,54 pp, além de perder 17,36 pp de recall.

**O que isso trava para o HANDOFF 04:** a comparação v1 × v2 é lida **sem vazamento**, e o
intervalo pareado e o McNemar rodam sobre esse modo. Acurácia não entra em nenhum veredito.

## O gate de escalonamento do HANDOFF 03: respondido

Os **+3,5 pp reproduzem** (+3,48 pp no teste, com vazamento). O gate não disparou e a execução
seguiu. A conclusão importante é que a afirmação do README é **verdadeira como afirmação de
acurácia** — e é exatamente por isso que o trabalho tem valor: o defeito não é um número errado,
é a métrica errada. Com prevalência de ~15 %, o preditor sempre-zero já acerta 84 % no teste.


## Em teste de vazamento, asserte a probabilidade — não a decisão

Regra geral do Bloco B, tirada da medição do D02:

| rótulos revistos | probabilidades que mudam | decisões que viram |
|---:|---:|---:|
| 2 | 3 | 0 |
| 8 | 128 | 0 |
| 21 | 168 | **1** |

A violação começa em **2** rótulos e a primeira decisão só vira em **21**. Assertar decisão exige
uma perturbação **10× maior** para acusar o mesmo defeito: o limiar de 0,5 funciona como filtro que
engole a evidência. A decisão é a variável que a planta consome, mas **a probabilidade é onde o
vazamento se manifesta primeiro**.

## Convenção de sinal do IC pareado — travar antes de escrever o HANDOFF 04

O SPEC §5 (V8) fixa a leitura: **`lo > 0` ⇒ v1 melhor; `hi < 0` ⇒ v2 melhor**. Portanto a
diferença é **`métrica(v1) − métrica(v2)`**, e `bootstrap_ci_pareado(y, pred_a, pred_b, …)` tem de
calcular `metric(pred_a) − metric(pred_b)` com **a = v1** e **b = v2**.

Com recall no teste **sem vazamento** de v1 = 0,9374 e v2 = 0,6977, a diferença é **+0,2397** e o
IC deve sair **inteiro positivo** → `lo > 0` → **v1 melhor, com significância**.

> **Armadilha:** é fácil descrever o mesmo resultado como "IC inteiro negativo, v2 pior" — o que
> é verdade em português e **falso** sob esta convenção, onde `hi < 0` significa v2 *melhor*.
> Inverter a ordem dos argumentos inverte o veredito do relatório sem que nenhum teste falhe:
> o intervalo continua excluindo zero, só muda de lado.

**As duas convenções coexistem de propósito, e por isso nenhuma coluna se chama "Δ".**
`evidencias/linha-de-base.md` usa **v2 − v1** nas tabelas descritivas, porque "a v2 ganhou
+3,5 pp" é como a Nortemec fala e é a frase que o trabalho contesta. O IC pareado usa **v1 − v2**,
que é o que o SPEC fixou. São o mesmo fato com o sinal trocado, em dois documentos que o relatório
cita lado a lado — e foi exatamente essa ambiguidade que produziu o erro de leitura.

A solução é **explicitação, não harmonização**: cada coluna carrega a fórmula no nome
(`acurácia(v2) − acurácia(v1), pp`; `recall(com) − recall(sem), pp`), e `linha-de-base.md` abre com
um aviso de convenção. Nenhuma coluna se chama apenas "Δ" — verificado por `grep`.

**O teste de referência tem de assertar o sinal, não só a ordem.** Em
`test_bootstrap_e_mcnemar_em_casos_de_referencia`, usar dois modelos sintéticos em que se sabe de
antemão qual é o melhor, e assertar que o IC sai do lado esperado. Fixar só a ordem dos argumentos
não protege: se alguém a inverter, o veredito muda em silêncio e o teste continua verde.

## Material de relatório: quatro oráculos que não matavam a hipótese

O enunciado paga por "formular uma hipótese e desenhar o teste que a mata". Em quatro casos o
**primeiro desenho não matava**, e os quatro têm a mesma forma — o oráculo mede com a ferramenta
errada e conclui o contrário:

| defeito | primeiro desenho | por que falhava em acusar | desenho que funciona |
|---|---|---|---|
| **D07** | comparar a decisão de **uma** linha | coincidem em ~46 % dos casos | varrer o lote e reportar a taxa (54,2 %) |
| **D09** | recortar **por motor** | as janelas já são por motor | recorte **temporal**, como a planta reprocessa |
| **D22** | sem descartar linha | o índice reconstruído coincide por acidente | criar a condição (descartar uma linha) |
| **D02** | renomear o motor / assertar decisão | renomear preserva a média do grupo; decisão engole a evidência | mexer só no rótulo e assertar **probabilidade** |

Isto é conteúdo do `relatorio.md` (HANDOFF 06), não nota de execução: é a evidência de que a suíte
foi desenhada contra hipóteses, e não escrita para passar.

## Por que a inflação do vazamento é exatamente 0,00 pp no treino

Não é coincidência, é consequência direta da medição dos limiares. `scripts/treinar.py` linha 72
grava `risco_maquina.json` como `round(médias do treino, 6)`. Logo, **no treino**, o recálculo por
lote e a tabela congelada diferem em no máximo **5e-07** — abaixo de qualquer corte da floresta, e
as probabilidades saem bit-idênticas. Fora do treino esse vínculo não existe: a tabela continua
sendo a do treino, o recálculo é do lote, e a distância entre as duas é grande.

**A magnitude do vazamento é literalmente a distância entre a tabela congelada e o recálculo do
lote.** No teste e em produção essa distância chega a 0,214286 na feature (0,428571 contra o teto
de 0,214286). Ressalva: os 2 nós da v2 que ficam a menos de 5e-07 de um valor da tabela são a única
via pela qual o arredondamento poderia virar decisão — medir no HANDOFF 04.

## `medicoes.json` tem dois produtores, e um apagava o outro

**Descoberto e corrigido no HANDOFF 04, Etapa 1** — mas o defeito é do HANDOFF 03.

`evidencias/medicoes.json` é escrito por **dois** processos diferentes:

| produtor | chaves que grava |
|---|---|
| `pytest_sessionfinish` (`conftest.py`) | `sut`, `contrato_dados`, `v1_v2`, `limiar`, `flip`, `drift`, `sensibilidade` |
| `scripts/linha_de_base.py` | `linha_de_base`, e `acuracia_sempre_zero` dentro de `contrato_dados` |

O `sessionfinish` escrevia `_MEDICOES` **por cima do arquivo inteiro**. Como `_MEDICOES` nasce com
`"linha_de_base": []`, qualquer `pytest` rodado depois do script zerava os 12 registros da linha de
base. E é a ordem natural: gera-se a linha de base, depois roda-se a suíte.

**O `medicoes.json` entregue no fim do HANDOFF 03 já estava com `linha_de_base: []`** — violando
SPEC C8, que lista a chave no esquema. Ninguém percebeu porque nenhuma verificação lia aquela chave:
V8 lê `v1_v2` e V15 lê `limiar`, as duas do outro produtor.

**Correção:** `conftest._fundir()`. Uma chave que a sessão **não** preencheu preserva o que estava
no arquivo; uma que ela preencheu substitui; dicionário funde por subchave, para que `-m unitario`
não apague o que `-m estatistico` mediu.

Isso **não** afrouxa S13: a mesma sequência de comandos com a mesma semente produz o mesmo arquivo,
e foi conferido — regenerada a linha de base, `diff` contra a anterior **vazio**, e depois de um
`pytest` a chave sobrevive com os 12 registros.

> **Consequência para o HANDOFF 06:** `scripts/evidencias.sh` tem de rodar os produtores em ordem e
> pode contar com a fusão. Mas quem quiser regenerar do zero precisa **apagar** o arquivo antes —
> a fusão preserva valor obsoleto em silêncio se um produtor deixar de rodar.

## `scripts/linha_de_base.py` só roda como módulo

```
$ python scripts/linha_de_base.py
ModuleNotFoundError: No module named 'suite'
$ python -m scripts.linha_de_base        # funciona
```

Rodando pelo caminho do arquivo, o `sys.path[0]` é `scripts/`, e `suite/` não é visto. Com `-m`, é
o diretório de trabalho (`/trabalho`) que entra no path. Sob `pytest` a questão não aparece porque a
rootdir já entra no path — é o mesmo mecanismo que faz
`from scripts.smoke import DIVERGENCIAS_CONHECIDAS` funcionar nos testes.

**Vale para o `scripts/evidencias.sh` do HANDOFF 06:** todo script desta árvore que importe `suite`
ou `scripts` se invoca com `python -m`.

## O custo assimétrico: por que FN vale 20× FP

**Travado no HANDOFF 04, Etapa 2.** O número entra em `test_limiar_de_custo_minimo_e_0_5` e na
coluna `custo` de `medicoes.json`, então não pode ser um chute não declarado.

`custo = 20 × falsos_negativos + 1 × falsos_positivos`

**A justificativa da planta**, nos termos do próprio enunciado: um falso negativo é **um motor
que queima** — parada não planejada, troca do ativo, produção parada enquanto a linha espera.
Um falso positivo é **uma equipe deslocada à toa** — algumas horas de técnico e uma inspeção
que não era necessária. As duas coisas não são da mesma ordem de grandeza, e tratá-las como
se fossem é exatamente o que o limiar 0,5 faz.

**Por que 20 e não outro número.** É a razão que o próprio SUT já embute em outro lugar: a
métrica F2 (β=2), que o SPEC adota, pesa recall **4×** precisão. 20 é a mesma decisão levada
ao domínio do custo, na ordem de grandeza em que manutenção industrial costuma operar (um
motor de linha contra algumas horas de equipe). Não é medido na Nortemec, e o relatório **tem
de declará-lo como premissa**, não como dado.

**O que protege a conclusão de depender do número.** A conclusão não muda numa faixa larga de
razões: a v1 tem custo mínimo em 0,50 e a v2 em 0,15, e a distância entre os dois é grande
(4.393 contra 1.788). Uma razão de 10× ou de 40× não inverteria isso. Se alguém contestar o 20,
a resposta é refazer a varredura com o número dele — é uma linha — e não redesenhar o teste.

> **Achado que contraria o HANDOFF 04.** O HANDOFF antecipava que "o limiar de custo mínimo com
> FN valendo 20× FP **não** é 0,5". Medido: **para a v1 é.** O 0,5 é ótimo para o modelo em
> produção, e deixa de ser ótimo justamente quando se promove a v2 sem retocá-lo. Ver D11 em
> `docs/mapa-defeitos.md`.

## O veredito v1 × v2, lido pela regra de C11

**Medido no HANDOFF 04, Etapa 3.** Conjunto **teste**, modo **sem vazamento**, `n_boot = 1000`,
`SUITE_SEED = 42`.

```
ic_recall   = [0.207485, 0.269825]      # recall(v1) − recall(v2)
mcnemar_p   = 1.0947644252537633e-47
discordantes = {'n01': 0, 'n10': 157}   # entre as falhas reais
```

**Veredito: `lo > 0` ⇒ a v1 é melhor, com significância.** Os dois métodos concordam. A
diferença pontual é +0,2397 de recall, exatamente a prevista quando esta seção foi escrita
antes da Etapa 3 — o intervalo `[0,2075; 0,2698]` não chega perto de zero.

**A promoção da v2 não se sustenta.** Não por uma diferença de acurácia mal lida, mas porque
não há **uma única** falha real que a v2 pegue e a v1 perca (`n01 = 0`): as 457 capturas da v2
são subconjunto das 614 da v1.

## McNemar global responde sobre acurácia — e dá o veredito oposto

**Correção de oráculo, descoberta na Etapa 3 do HANDOFF 04.** É o quinto caso da família
"o primeiro desenho não matava a hipótese", e o mais perigoso de todos: aqui o oráculo errado
não deixava de acusar, ele **acusava ao contrário**.

`test_mcnemar_concorda_com_o_intervalo_pareado` (SPEC §4.2) é um teste **verde**: os dois
métodos têm de dar o mesmo veredito. Rodando McNemar sobre o lote inteiro, não dão:

| McNemar sobre | n01 | n10 | p | aponta |
|---|---:|---:|---|---|
| o lote inteiro (4.200 linhas) | 512 | 157 | 8,7e-45 | **v2** |
| só as falhas reais (655 linhas) | **0** | 157 | 1,1e-47 | **v1** |

Não é contradição, e nenhum dos dois está errado como cálculo. **São perguntas diferentes.**
McNemar sobre acerto bruto compara **acurácia** — e a v2 é mais acurada, é o fato de onde saiu
toda a confusão da Nortemec. O IC pareado desta fase é do **recall**. Comparar os dois
vereditos é comparar respostas a perguntas distintas.

**A regra que fica:** o McNemar tem de ser restrito ao subconjunto sobre o qual a métrica do IC
é definida. Recall é definido sobre os positivos reais, então o McNemar do recall olha
`y == 1`. Se um dia a comparação passar a ser de precisão, o recorte muda para `pred == 1`.

> O teste, escrito como o SPEC o descreve mas com o McNemar global, **falharia** — e a leitura
> natural seria "os métodos discordam, algo está quebrado". Estaria tudo certo, exceto a
> pergunta. Vale parágrafo no `relatorio.md`: é o exemplo mais limpo de que **a estatística não
> protege de medir a coisa errada**.

## Forma final dos testes de estabilidade (a decisão que o SPEC §8 deixou para a execução)

**Decidido no HANDOFF 04, Etapa 4**, que manda "decidir aqui, conforme o número medido".

Os números:

| grandeza | treino | teste | producao | teste × producao | treino × teste |
|---|---:|---:|---:|---:|---:|
| dropout de vibração | 0,0724 | 0,0971 | 0,0840 | 1,31 p.p. | **2,47 p.p.** |
| proporção em psi | 0,3200 | 0,3200 | 0,3200 | 0,00 p.p. | 0,00 p.p. |
| prevalência do alvo | 0,1154 | 0,1560 | 0,1426 | 1,34 p.p. | **4,06 p.p.** |

**A decisão: os três testes assertam `teste × producao`, com a tolerância de 2 p.p. do SPEC, e
registram os três conjuntos em `medicoes.json`.**

O motivo não é que o par passa e o outro não — seria escolher a régua depois de ver o
resultado. É que **`teste × producao` é a pergunta que este arquivo faz**, do primeiro teste
ao último: `teste` é o baseline e `producao` é o que se compara contra ele. Misturar `treino`
nos mesmos asserts responderia duas perguntas com um número só, e a segunda (descasamento
**treino/serviço**) é de outra natureza.

**O que seria desonesto é omitir os dois números que estouram a tolerância, e eles não são
omitidos:** entram na mensagem do assert, em `medicoes.json → estabilidade` e nesta tabela.

**O que treino × teste diz, e onde ele é tratado.** Prevalência de 11,54 % no treino contra
15,60 % no teste (4,06 p.p.) e dropout de 7,24 % contra 9,71 % (2,47 p.p.). O modelo foi
treinado numa população com menos falhas e menos buracos de sensor do que aquela em que foi
avaliado. Isso **não é drift de produção** — é como os conjuntos foram partidos — e conversa
diretamente com o achado do Bloco A de que o conjunto de teste é o único sem violação de
ficha. Material do `relatorio.md`, não assert desta fase.

## A estabilidade do veredito: 200 de 200

`test_veredito_estatistico_e_estavel_em_duzentas_sementes`, marker `lento`, 9,2 s:

```
{'veredito': 'a_melhor', 'concordantes': 200, 'sementes': 200, 'contagem': {'a_melhor': 200}}
```

Rodado com **`n_boot=200`**, e não com os 1.000 do teste de verdade, de propósito: o que se
mede é a estabilidade do **veredito** sob a semente, não a precisão do intervalo. Menos
reamostragens dão um intervalo mais largo, o que torna a verificação **mais exigente** — um
veredito que sobrevive ao intervalo largo sobrevive ao estreito.

**O McNemar não entra nesta prova** e a ausência é deliberada: ele é exato, não reamostra
nada, e portanto não tem semente de que depender. Submetê-lo a um teste de estabilidade de
semente sugeriria que ele tem uma.

## A v2 não domina a v1 em limiar nenhum — insumo dos HANDOFFs 05/06

**Calculado em 20260924** da varredura de limiar que a Etapa 2 do HANDOFF 04 gravou em
`medicoes.json` (38 pontos, 19 por versão). Não roda nada novo: é leitura da evidência que já
existe. Levantado numa revisão posterior e conferido contra o disco.

**A objeção que isto fecha.** Hoje a conclusão tem a forma "a v2 é pior **no limiar 0,5**", e a
réplica natural de quem defende a promoção é: *vocês só não reajustaram o limiar da v2*. Metade
da réplica já estava morta (o 0,5 é o ótimo da v1, não um default distraído). Esta é a outra
metade.

| ponto de operação | custo | recall | precisão |
|---|---:|---:|---:|
| v1 @ 0,50 — **mínimo da v1** | **1.765** | 0,937405 | 0,393842 |
| v2 @ 0,50 (limiar herdado) | 4.393 | 0,697710 | 0,513450 |
| v2 @ 0,15 — **mínimo da v2** | 1.788 | **0,937405** | 0,388116 |

```
pontos da v2 com custo menor que o melhor da v1: 0 de 19
razão v2@0,50 / v1@0,50 = 2,489
```

**Reajustada para 0,15, a v2 recupera exatamente o recall da v1** — 0,937405 nas duas, que é
`614/655`, o mesmo número de falhas pegas. E ainda assim perde no custo (1.788 contra 1.765),
porque a precisão nesse ponto é um pouco pior: paga a mesma detecção com mais ordens em vão.
**Nenhum dos 19 pontos da v2 bate o melhor da v1.**

Isso também resolve a tensão da calibração: a saída óbvia para "a v2 é mais bem calibrada"
(ver D12) é *então é só mexer no limiar* — e está medido que não é. O que a calibração melhor
da v2 compra é **confiança na probabilidade**, não **capacidade de detecção**.

> ### Ressalva que o relatório não pode perder: `n01 = 0` é do ponto de operação, não da v2
>
> Tentador abrir o relatório com "a v2 não pega um único motor que a v1 deixe passar". A frase
> é verdadeira **no limiar 0,5**, que é onde o sistema opera — e é aí que ela vale. **Não** é
> uma propriedade da v2:
>
> ```
> v2@0,50 vs v1@0,50 -> n01 = 0    n10 = 157   (pegas: v1 614, v2 457)
> v2@0,15 vs v1@0,50 -> n01 = 7    n10 =   7   (pegas: v1 614, v2 614)
> ```
>
> No ótimo dela, a v2 pega **outras** 614 falhas: 7 que a v1 perde, e perde 7 que a v1 pega.
> Escrever a frase sem "no limiar em que o sistema opera" seria o mesmo tipo de
> generalização indevida que este trabalho acusa na Nortemec. As duas afirmações convivem: no
> ponto de operação a v2 é estritamente dominada, e em **nenhum** ponto ela domina.

**Teste sugerido para o HANDOFF 05 ou 06** (verde, barato, e é o que a banca pergunta):
`test_nenhum_limiar_da_v2_domina_a_v1`, assertando `min(custo_v2) >= min(custo_v1)` sobre a
varredura inteira. Endurecimento opcional, que transforma a premissa do 20× em resultado com
domínio de validade declarado: varrer a razão de custo (5×, 10×, 20×, 50×) e reportar em quais
faixas a conclusão se mantém.

### No empate de recall, a v2 erra **diferente** — não erra mais

Medido em 20260924, cada modelo no seu próprio ótimo de custo (v1 @ 0,50, v2 @ 0,15), sobre as
**655** falhas reais do conjunto de teste:

```
v1 pega 614 | v2 pega 614
interseção (os dois pegam): 607
união (ao menos um pega):   621
só v1: 7    só v2: 7    nenhum dos dois: 34
```

Os dois pegam 614 das mesmas 655, mas **não as mesmas 614**. Existem 7 motores que só a v2
pega. Isso é mais forte que "a v2 é pior": no ponto em que empatam no recall, ela erra em
lugares diferentes.

**A conclusão que os dados sustentam, e a que eles não sustentam.** Um relatório que conclui
"a v2 é um modelo ruim" repete o erro da Nortemec com o sinal invertido — e este arquivo já
registra por que: a v2 é a **mais bem calibrada** (D12), ranqueia melhor no conjunto de teste
(PR-AUC +9,07 pp), e no limiar certo detecta tanto quanto a v1. O defeito nunca foi a v2.

O defeito é **ter decidido por acurácia**, que é cega para tudo isto de uma vez: cega para a
perda de recall no limiar herdado, cega para a calibração, cega para o fato de que os dois
modelos erram em conjuntos diferentes. A conclusão defensável é: *a decisão foi tomada com o
instrumento errado, e o instrumento certo mostra que a v2 não compra nada — nem mesmo
reajustada.*

> Material de redação do `relatorio.md` (HANDOFF 06). **Não vira teste**: não há defeito do SUT
> aqui, e a interseção de 607 não é uma invariante que se queira travar — é uma descrição do
> par de modelos neste conjunto.

## Convenções do Bloco C, e o que o HANDOFF 06 herda

**Decidido no HANDOFF 05, 20260925.**

### A perturbação é uniforme, e isso é o oráculo

`perturbacao.perturbar_coluna` sorteia em `[-amplitude, +amplitude]`, uniforme, **não**
gaussiano. A afirmação sob teste é "perturbação **estritamente menor** que o ruído de
±1,0 °C não muda a decisão". Uma gaussiana de σ = 0,4 tem cauda infinita: parte dos sorteios
passaria de 1,0 °C, e um flip causado por essa cauda seria **legítimo** — o oráculo perderia
o direito de chamar aquilo de defeito. Com o uniforme, `|ruído| <= amplitude` vale para todas
as linhas por construção. Medido: `|ruído| máx = 0,399812` para amplitude 0,4.

### Para feature binária, "±1 desvio-padrão" é inverter

O primeiro ranking de sensibilidade somava ruído de ±1 sd às treze features e devolveu
`operador_senior` com `delta_medio = 0,000000`, **em último lugar** — enquanto o
contrafactual de D06 virava 155 decisões com ela. A feature é binária e ruído de ±0,43 em
torno de 0 ou de 1 nunca cruza o corte em 0,5. **O instrumento estava cego exatamente à
feature que interessava.** Corrigido: binária é invertida, contínua leva ±1 sd. Com isso
`operador_senior` sobe a **1ª de 13 nas duas versões**.

Regra geral: antes de aplicar uma perturbação uniforme a um conjunto de features, confira o
**tipo** de cada uma. A régua que serve para uma contínua não serve para uma categórica.

### Sexto caso de "o primeiro desenho não matava a hipótese" — D04

Acrescenta-se aos cinco já tabelados (D07, D09, D22, D02, McNemar global):

| defeito | primeiro desenho | por que falhava | desenho que funciona |
|---|---|---|---|
| **D04** | apagar **uma** leitura e assertar a **decisão** das 24 h afetadas | `vib_media_6h` move 2,09 °C e a probabilidade 0,0239 — o limiar de 0,5 engole; 0 decisões viram | trocar a **constante de imputação** (0,0 → 1,2 mm/s) nas **408** ausências que o historiador já entregou: 10 e 29 decisões viram |

É a mesma lição de D02 por outro caminho: **a decisão é a variável que a planta consome, mas
a evidência do defeito aparece antes dela.** Quando o assert de decisão passar, refaça o
experimento perguntando "o que, nesta escolha arbitrária, está decidindo?" em vez de
"perder este dado muda algo?".

### `n01 = 0` ganhou um irmão: `0↑/57↓` também é do ponto de operação

O contrafactual de D06 é **estritamente direcional** — apagar o nome do sênior só faz alarme
sumir, nunca aparecer, nas duas versões. A frase para o relatório é forte e é verdadeira **no
limiar 0,5**. Vale a mesma ressalva já registrada para `n01 = 0`: é uma propriedade do ponto
de operação, medida ali, e o relatório deve dizê-lo.

### O que o HANDOFF 06 herda daqui

- **`medicoes.json` cresceu com a chave `contrafactual`** (`operador`, `pressao_unidade`,
  `dropout_vibracao`, cada um `{versao: {taxa, para_cima, para_baixo}}`, mais
  `taxa_falha_por_operador`) e `sensibilidade` ganhou `versao`. O `scripts/evidencias.sh`
  precisa rodar `-m adversarial` **e** `-m lento` para preencher as duas: `sensibilidade` só é
  escrita pelo teste `lento`, e a fusão de `conftest._fundir` preserva valor obsoleto em
  silêncio se o produtor não rodar. Quem regenerar do zero **apaga o arquivo antes**.
- **Os 23 IDs de D01 a D23 estão cobertos** (V5): 58 xfail em 43 funções. O relatório pode
  afirmar cobertura completa do catálogo.
- **D06, D14 e D21 não têm patch, e isso é deliberado** — corrigir os três exigiria retreinar
  ou alterar o SUT, o que viola C12 e derrubaria V11. Mesma decisão já tomada para D23.
- **Material de redação já medido, que não precisa ser recalculado:** a tabela de flip por
  amplitude/versão/direção (D14), a taxa de falha por operador (D06), a extensão do dropout
  (**71,5 %** do lote na janela de influência de algum `0,0`), e o ranking de sensibilidade.
  Tudo em `docs/mapa-defeitos.md` e em `medicoes.json`.
- **Uma previsão do HANDOFF 05 não se confirmou e o relatório não deve repeti-la:**
  `maquina_risco` **não** está entre as features mais influentes do ranking de perturbação
  (6ª na v1, 7ª na v2, de 13). O argumento contra ela se sustenta pelo vazamento de alvo
  (D02) e pela degeneração em lote de uma linha (D15), não por sensibilidade.
- **Pendência herdada do HANDOFF 04 que continua aberta:** os **2 nós da v2** a menos de
  5e-07 de um valor da tabela arredondada — o único caminho pelo qual o arredondamento de
  `risco_maquina.json` poderia virar decisão. O HANDOFF 04 a deixou para o Bloco C e o
  HANDOFF 05 **não a mediu**: nenhuma das cinco etapas a cobre, e medi-la seria expandir
  escopo de fase. Fica anotada aqui para o 06 decidir — é barata (leitura dos dois limiares
  contra a tabela) e rende um parágrafo de magnitude no relatório.


## `make evidencias` é o último comando, sempre

**Descoberto no HANDOFF 06, e de novo no ajuste pós-fechamento — duas vezes, pelo mesmo mecanismo.**

`pytest_sessionfinish` grava `SUITE_MEDICOES` ao fim de **toda** sessão de pytest. O serviço `suite`
do compose roda com `SUITE_N_BOOT=1000`; o alvo `evidencias`, com **2000**. Logo, qualquer rodada
avulsa — inclusive as verificações `V<n>` que o próprio método manda executar — **substitui**
`v1_v2` pelo intervalo de outra configuração.

Aconteceu duas vezes:

| quando | sintoma | como apareceu |
|---|---|---|
| durante a Validação final do H06 | `medicoes.json` 7 h à frente dos outros seis artefatos, com `ic_recall` de `n_boot=1000` enquanto o relatório citava o de 2000 | o humano comparou os **mtimes** dos sete arquivos |
| na reconferência do ajuste | idem, minutos depois | o campo `sut.n_boot`, acrescentado justamente para isso |

**A fusão de `conftest._fundir` não protege disto.** Ela impede que um produtor apague as chaves de
outro; não impede que uma rodada **preencha a mesma chave** com um número de outra configuração.

### As duas regras que ficam

1. **`make evidencias` é o último comando de qualquer sessão** que vá entregar ou citar números.
   Ele apaga `medicoes.json`, roda os produtores em ordem e fecha os sete artefatos juntos.
2. **Antes de citar qualquer número, confira `sut.n_boot`.** Se não for 2000, o arquivo não é o
   conjunto oficial:

   ```bash
   python -c "import json;print(json.load(open('evidencias/medicoes.json'))['sut'])"
   ```

`sut.semente` e `sut.n_boot` foram acrescentados a C8 exatamente para tornar isto **detectável em
vez de silencioso**. Sem eles, os dois episódios acima seriam invisíveis.

> **Consequência para quem for seguir o README** (o HANDOFF 07 é isso): os Passos 4, 5 e 6 rodam a
> suíte e **vão** regravar `medicoes.json` com `n_boot=1000`. Isso é esperado e não quebra nada — os
> logs colados no README e o relatório seguem válidos. Para restaurar o conjunto oficial:
> `make evidencias`.
