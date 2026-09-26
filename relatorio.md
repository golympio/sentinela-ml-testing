# Relatório — suíte de testes do Sentinela (TAU, Trilha 1)

**Sistema sob teste:** `felipehp/sentinela-nortemec` @ `c9020d7ba3bb4e6fd4ae22d46346a787b16adc02`
**Suíte:** 123 funções de teste em 14 arquivos, 231 ids · `170 passed, 61 xfailed`, exit 0, em 31,09 s
**Defeitos:** 24 (D01–D24), cada um com um teste que falha e um número medido
**Como reproduzir:** `docker compose run --rm suite` · ver [`README.md`](README.md)

> **Nenhum número deste relatório foi escrito à mão.** Todos saem de
> [`evidencias/medicoes.json`](evidencias/medicoes.json), de
> [`evidencias/linha-de-base.md`](evidencias/linha-de-base.md) ou — só os do anexo §11 — de
> [`evidencias/log-correcoes.txt`](evidencias/log-correcoes.txt), gerados por `make evidencias` com
> `SUITE_SEED=42` e `SUITE_N_BOOT=2000`. Duas execuções com a mesma semente produzem `medicoes.json`
> byte a byte idêntico (sha256 `681d1ae638ef1259d4ad68517691ac533ba6fc01218b3c0e09e11922026f48af`).
> Conferir: `sha256sum evidencias/medicoes.json`. **Qualquer `docker compose run` avulso regrava o
> arquivo** com `n_boot=1000` e muda o hash; `make evidencias` o restaura.

---

## 1. Resumo executivo

A Nortemec quer promover a **v2** porque ela tem **+3,5 pp de acurácia** sobre a v1 no conjunto de
teste. O número **reproduz**: medimos **+3,48 pp**, exatamente como a equipe mediu.

**A afirmação é verdadeira e a decisão é errada.** Com prevalência de ~15 %, um modelo que **nunca**
prevê falha já acerta **84,40 %** no conjunto de teste. Acurácia é quase insensível à classe que
importa, e é a única lente pela qual a v2 parece melhor.

Olhando pela lente certa — recall, que é o que responde "quantos motores a gente pega antes de
queimar" — a v2 **regride**, e a regressão tem significância:

```
ic_recall    = [0.206878, 0.270395]      # recall(v1) − recall(v2), bootstrap pareado, n=2000
mcnemar_p    = 1.0947644252537633e-47
discordantes = {'n01': 0, 'n10': 157}
```

O intervalo é **inteiro positivo**, logo pela regra fixada em SPEC §5 (`lo > 0` ⇒ v1 melhor) a **v1 é
melhor, com significância**. Os dois métodos concordam. O veredito é estável em **200 de 200**
sementes.

E o número que carrega o argumento é **`n01 = 0`**: no limiar em que o sistema opera, **não existe
uma única falha real que a v2 pegue e a v1 perca**. As 457 capturas da v2 são subconjunto das 614 da
v1, sobre 655 falhas reais.

### O que este relatório **não** conclui

**Não concluímos que a v2 é um modelo ruim.** Ela é a **mais bem calibrada** das duas (Brier
0,091652 contra 0,152340; ECE 5,76 p.p. contra 19,06 p.p.), ranqueia melhor no conjunto de teste
(PR-AUC +9,07 pp) e, reajustada ao seu próprio limiar ótimo, detecta **exatamente tanto quanto a
v1** — 614 de 655 nas duas.

Concluir "a v2 é ruim" repetiria o erro da Nortemec com o sinal trocado: decidir sobre um modelo a
partir de um número só. **O defeito nunca foi a v2. O defeito foi decidir por acurácia** — uma
métrica cega, de uma vez, para a perda de recall no limiar herdado, para a calibração, e para o fato
de que os dois modelos erram em conjuntos diferentes.

A conclusão que os dados sustentam é: *a decisão foi tomada com o instrumento errado, e o
instrumento certo mostra que a v2 não compra nada — nem mesmo reajustada.*

### Os cinco achados que sustentam tudo

| ID | Achado | Evidência medida |
|---|---|---|
| **D01** | **Vazamento temporal.** `rolling(6, center=True)` faz a janela ser `[t−2, t+3]` | `temp_media_6h[t=20]` muda **3,3333 °C** ao perturbar **apenas** `t+1..t+123` |
| **D02** | **Vazamento de alvo.** `maquina_risco` é recalculada a partir da coluna de rótulo | PR-AUC da v1 no teste vai de 0,5811 para 0,8679 (**+28,68 pp**) |
| **D11** | A promoção foi decidida por acurácia sobre classe rara | IC `[0,2069; 0,2704]`, McNemar `p = 1,1e-47`, **`n01 = 0`** |
| **D14** | A decisão muda **dentro do erro do próprio sensor** | a **±0,1 °C** — um décimo do ruído declarado de ±1,0 °C — a v1 vira **12** decisões e a v2, **18** |
| **D06** | O modelo lê **quem estava de plantão**, não o motor | trocar OP-07 por OP-03 com os sete sensores bit-idênticos apaga **57** (v1) e **155** (v2) alarmes, **todos para baixo** |

---

## 2. O que foi testado, e por quê

O enunciado fixa três blocos obrigatórios. Cada um responde a uma pergunta diferente sobre o mesmo
sistema, e a ordem importa: **não se faz afirmação estatística sobre um pipeline cujo contrato de
dados não foi verificado.**

| Bloco | A pergunta | Onde |
|---|---|---|
| **A — unitários** | O pipeline faz o que promete? A feature de `t` usa só leituras até `t`? | 51 funções em 5 arquivos |
| **B — estatísticos** | A v2 é melhor? Com que incerteza? O limiar é o certo? A probabilidade é probabilidade? Produção ainda é o teste? | 30 funções em 4 arquivos |
| **C — adversariais** | A decisão é estável dentro do erro do sensor? Depende de campo que não muda o motor? Aguenta os limites? | 17 funções em 2 arquivos |

Fora dos blocos, mais 25 funções: reprodutibilidade do ambiente (5), propriedades com `hypothesis`
(6) e testes dos **nossos próprios** helpers (14) — porque um helper errado invalidaria toda a
análise estatística, e um teste que não pode falhar não é teste.

### Uma premissa declarada: "sem vazamento" é simulação

O alvo `falha_72h` vem no CSV dos **três** conjuntos, inclusive `producao`. Para medir o que a planta
obteria de verdade, a suíte remove a coluna deliberadamente antes de construir as features, na ordem
*limpar com rótulo → extrair `y` → construir sem rótulo* (`suite/harness.py`).

**Isso é uma simulação do serving, e é declarada como tal.** Em produção o rótulo não existe porque a
falha ainda não aconteceu; aqui ele existe e é escondido. A simulação é validada: sobre um lote **sem**
a coluna de rótulo, os dois modos devolvem probabilidade e decisão **idênticas** (`array_equal` True)
nas duas versões — prova de que a diferença medida vem do rótulo, e não de um defeito do nosso
harness.

**Toda comparação v1 × v2 neste relatório é lida sem vazamento**, porque é esse o número que a planta
obtém.

### Convenção de sinal

[`evidencias/linha-de-base.md`](evidencias/linha-de-base.md) usa **v2 − v1** nas tabelas descritivas,
porque "a v2 ganhou +3,5 pp" é a frase que este trabalho contesta. O intervalo de confiança pareado
usa a convenção oposta, **v1 − v2**, fixada pelo SPEC §5. São o mesmo fato com o sinal trocado — e por
isso **nenhuma coluna se chama apenas "Δ"**: cada uma carrega a fórmula no nome.

---

## 3. Linha de base honesta

Doze linhas: três conjuntos × duas versões × com/sem vazamento. É a tabela de que tudo depende, e
**nenhum número entrou em assert sem passar por ela**.

| conjunto | linhas | prevalência | acurácia do preditor sempre-zero |
|---|---:|---:|---:|
| treino | 16.800 | 0,1154 | 0,8846 |
| teste | 4.200 | 0,1560 | **0,8440** |
| producao | 4.200 | 0,1426 | 0,8574 |

| conjunto | versão | vazamento | acurácia | precisão | recall | F1 | F2 | PR-AUC | Brier | ECE |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| treino | v1 | com | 0,9196 | 0,5899 | 0,9948 | 0,7406 | 0,8748 | 0,9413 | 0,0517 | 0,1084 |
| treino | v1 | sem | 0,9196 | 0,5899 | 0,9948 | 0,7406 | 0,8748 | 0,9413 | 0,0517 | 0,1084 |
| treino | v2 | com | 0,9857 | 0,9748 | 0,8994 | 0,9356 | 0,9136 | 0,9914 | 0,0162 | 0,0460 |
| treino | v2 | sem | 0,9857 | 0,9748 | 0,8994 | 0,9356 | 0,9136 | 0,9914 | 0,0162 | 0,0460 |
| teste | v1 | com | 0,8860 | 0,5832 | 0,9420 | 0,7204 | 0,8388 | 0,8679 | 0,0863 | 0,1355 |
| **teste** | **v1** | **sem** | 0,7652 | 0,3938 | **0,9374** | 0,5547 | 0,7346 | 0,5811 | 0,1523 | 0,1906 |
| teste | v2 | com | 0,9207 | 0,7164 | 0,8137 | 0,7620 | 0,7922 | 0,8117 | 0,0685 | 0,0716 |
| **teste** | **v2** | **sem** | 0,8498 | 0,5135 | **0,6977** | 0,5916 | 0,6510 | 0,6718 | 0,0917 | 0,0576 |
| producao | v1 | com | 0,8581 | 0,5013 | 0,9800 | 0,6633 | 0,8228 | 0,7728 | 0,0935 | 0,1400 |
| producao | v1 | sem | 0,8174 | 0,4354 | 0,9449 | 0,5961 | 0,7657 | 0,6433 | 0,1259 | 0,1693 |
| producao | v2 | com | 0,8660 | 0,5186 | 0,8381 | 0,6407 | 0,7461 | 0,7198 | 0,0820 | 0,0823 |
| producao | v2 | sem | 0,8569 | 0,4989 | 0,7713 | 0,6059 | 0,6954 | 0,6379 | 0,0877 | 0,0717 |

### A inflação do vazamento é exatamente 0,00 pp no treino — e não é coincidência

`scripts/treinar.py` grava `risco_maquina.json` como `round(médias do treino, 6)`. Logo, **no
treino**, a tabela congelada **é** a média por motor do próprio treino: o recálculo por lote e a
tabela diferem em no máximo **4,762e-07** — abaixo de qualquer corte da floresta — e as
probabilidades saem **bit-idênticas**.

Fora do treino esse vínculo não existe, e a inflação é grande:

| conjunto | versão | recall(com) − recall(sem) | F2 | PR-AUC | acurácia |
|---|---|---:|---:|---:|---:|
| teste | v1 | +0,46 pp | +10,41 pp | **+28,68 pp** | +12,07 pp |
| teste | v2 | +11,60 pp | +14,12 pp | +13,99 pp | +7,10 pp |
| producao | v1 | +3,51 pp | +5,71 pp | +12,95 pp | +4,07 pp |
| producao | v2 | +6,68 pp | +5,08 pp | +8,20 pp | +0,90 pp |

---

## 4. Bloco A — o contrato de dados e os unitários

### O conjunto de teste é o único limpo, e é nele que a v2 foi medida

Não é detalhe de marcação. Violações da ficha técnica existem em **treino** e em **produção**, e
**zero** no conjunto de teste:

| conjunto | linhas | rpm fora de faixa | pressão convertida fora de faixa |
|---|---:|---:|---:|
| treino | 16.800 | 4 | 5 |
| **teste** | 4.200 | **0** | **0** |
| producao | 4.200 | 1 | 1 |

O conjunto de teste é exatamente onde a Nortemec mediu os +3,5 pp. Quem só olha a métrica de teste —
que foi o que aconteceu — **nunca vê a violação**: ela está no dado com que o modelo foi treinado e
volta no dado que ele vê em produção. É o caso concreto da tese desta entrega: *a métrica de teste
não descreve o sistema.*

### O teste-estrela: a feature de `t` usa o futuro

A pergunta literal do enunciado. O oráculo não depende da versão do `pandas` nem do offset da janela
par: perturba-se **apenas** o futuro (`t+1..t+123`, em +10 °C) e exige-se que `t` não se mova.

```
AssertionError: temp_media_6h[t=20] mudou 3.3333 °C ao perturbar APENAS t+1..t+123
em +10.0 °C; 29 linhas do lote mudaram no total
```

**Dois controles positivos passam no mesmo experimento** — `temp_max_24h` e `vib_media_6h`, mesmas
janelas, sem `center=True`. É o que isola a causa: não é "janela móvel vaza", é `center=True`.

---

## 5. Bloco B — incerteza, limiar, calibração e drift

### 5.1 O veredito v1 × v2, com incerteza

Conjunto **teste**, modo **sem vazamento**, `n_boot = 2000`, `SUITE_SEED = 42`.

```
ic_recall    = [0.206878, 0.270395]      # recall(v1) − recall(v2)
mcnemar_p    = 1.0947644252537633e-47
discordantes = {'n01': 0, 'n10': 157}
```

Pela regra de leitura da aula 4, fixada em SPEC §5: **`lo > 0` ⇒ v1 melhor, com significância.** O
intervalo não chega perto de zero. Os dois métodos concordam, e o veredito é **estável em 200 de 200
sementes**.

#### O McNemar teve de ser restrito, e o erro que isso evitou é o exemplo mais limpo do trabalho

Calculado sobre o lote inteiro, o McNemar dá o veredito **oposto**:

| McNemar sobre | n01 | n10 | p | aponta |
|---|---:|---:|---|---|
| o lote inteiro (4.200 linhas) | 512 | 157 | 8,7e-45 | **v2** |
| só as falhas reais (655 linhas) | **0** | 157 | 1,1e-47 | **v1** |

Nenhum dos dois está errado como cálculo. **São perguntas diferentes.** McNemar sobre acerto bruto
compara **acurácia** — e a v2 é mais acurada, é o fato de onde saiu toda a confusão da Nortemec. O
intervalo pareado é do **recall**, que é definido sobre os positivos reais. A regra que fica: *o
McNemar tem de ser restrito ao subconjunto sobre o qual a métrica do intervalo é definida.*

Escrito como o primeiro desenho pedia, o teste **falharia**, e a leitura natural seria "os métodos
discordam, algo está quebrado". Estaria tudo certo, exceto a pergunta. **A estatística não protege de
medir a coisa errada.**

#### Ressalva obrigatória: `n01 = 0` é do ponto de operação, não da v2

É tentador escrever "a v2 não pega um único motor que a v1 deixe passar". A frase é verdadeira **no
limiar 0,5**, que é onde o sistema opera — e é aí que ela vale. **Não** é propriedade da v2:

```
v2@0,50 vs v1@0,50 -> n01 = 0    n10 = 157   (pegas: v1 614, v2 457)
v2@0,15 vs v1@0,50 -> n01 = 7    n10 =   7   (pegas: v1 614, v2 614)
```

No ótimo dela, a v2 pega **outras** 614 falhas: 7 que a v1 perde, e perde 7 que a v1 pega
(interseção 607, união 621, nenhum dos dois pega 34). As duas afirmações convivem: **no ponto de
operação a v2 é estritamente dominada, e em nenhum ponto ela domina.** Escrever a primeira sem a
segunda seria a mesma generalização indevida que este trabalho acusa na Nortemec.

### 5.2 O limiar de decisão

O limiar é `0.5` porque alguém escreveu `0.5`. Varremos de 0,05 a 0,95 (19 pontos por versão, 38 no
total), com `custo = 20 × FN + 1 × FP`.

> **O 20× é premissa declarada, não dado medido na Nortemec.** Um falso negativo é um motor que
> queima — parada não planejada, troca do ativo, linha parada. Um falso positivo é uma equipe
> deslocada à toa — algumas horas de técnico. É a mesma razão que o F2 (β=2) já embute ao pesar
> recall 4× precisão, levada ao domínio do custo. **A conclusão não depende do número**: numa faixa
> de 10× a 40× o ordenamento não muda.

| ponto de operação | custo | recall | precisão | F2 |
|---|---:|---:|---:|---:|
| **v1 @ 0,50 — mínimo da v1** | **1.765** | 0,937405 | 0,393842 | 0,734626 |
| v2 @ 0,50 (limiar herdado) | 4.393 | 0,697710 | 0,513483 | 0,650997 |
| v2 @ 0,15 — mínimo da v2 | 1.788 | 0,937405 | 0,388116 | 0,730604 |

**Dois achados, e o primeiro contraria o que esperávamos.** Previmos que o limiar de custo mínimo não
seria 0,5. **Para a v1, é** — exatamente 0,50. O 0,5 não é um default distraído: é o ótimo do modelo
em produção, e deixa de ser ótimo justamente quando se promove a v2 sem retocá-lo. **Promover a v2
herdando esse limiar custa 2,5× mais.**

O segundo fecha a réplica natural — *vocês só não reajustaram o limiar da v2*: **nenhum dos 19 pontos
da v2 bate o melhor da v1.** Reajustada para 0,15 ela recupera exatamente o recall da v1 (0,937405,
os mesmos 614 de 655) e **ainda assim perde no custo**, porque paga a mesma detecção com mais ordens
em vão.

### 5.3 Calibração — e o resultado que inverte o ranking

| versão | Brier | ECE | faixas com gap positivo |
|---|---:|---:|---:|
| v1 | 0,152340 | 19,06 p.p. | 10 de 10 |
| **v2** | **0,091652** | **5,76 p.p.** | 10 de 10 |

**A v2 é a mais bem calibrada, e é a que deixa passar motor.** "Melhor calibrado" ≠ "melhor para a
planta" — e é exatamente por isso que o Bloco B não pode ser resumido a uma métrica só, que é o erro
que ele está diagnosticando.

O que se sustenta sem ressalva é a **superconfiança**: **20 de 20 faixas** (10 por versão) têm gap
positivo. As duas versões prometem mais risco do que existe, em toda a escala. A faixa 0,2–0,3 da v1
é o caso extremo: ela promete 24,72 % e a frequência observada é **0,00 %**.

### 5.4 Drift — e por que os três detectores vão juntos

`teste` (baseline) contra `producao`:

| coluna | Δ relativo | média acusa? | KS `p` | KS acusa? | PSI | classe |
|---|---:|---|---:|---|---:|---|
| corrente_a | 0,52 % | não | 3,19e-11 | **sim** | 0,0575 | estável |
| idade_equipamento_meses | 0,00 % | não | 1,00 | não | 0,0000 | estável |
| pressao | 0,65 % | não | 1,60e-05 | **sim** | 0,0520 | estável |
| rpm | 0,05 % | não | 9,76e-07 | **sim** | 0,0203 | estável |
| **temperatura_c** | 1,76 % | não | **3,53e-33** | **sim** | **0,1798** | **atenção** |
| **vibracao_rms** | 2,05 % | não | 1,14e-21 | **sim** | **0,1403** | **atenção** |

**A diferença de médias fica calada em 6 de 6 colunas.** A maior é 2,05 %, contra um limiar de 10 %.
O KS acusa **5**, o PSI põe **2** em atenção. Um monitoramento feito sobre médias — o primeiro que
qualquer equipe escreve, por ser o mais barato — diria "tudo estável" com cinco das seis entradas
mudadas de distribuição.

**E o KS sozinho enganaria na direção oposta:** `p = 3,53e-33` parece catástrofe, e o PSI
correspondente é 0,18 — *atenção*, não drift severo. Com n = 4.200 por lado, p minúsculo é o esperado
de qualquer diferença real. Por isso o tamanho do efeito vai **ao lado** do p, sempre.

#### O que não é drift, e por isso não entra aqui

Treino × teste estoura a tolerância em duas grandezas — dropout de vibração 7,24 % contra 9,71 %
(2,47 p.p.) e prevalência 11,54 % contra 15,60 % (**4,06 p.p.**). Isso **não é drift de produção**: é
como os conjuntos foram partidos. O modelo foi treinado numa população com menos falhas e menos
buracos de sensor do que aquela em que foi avaliado — descasamento **treino/serviço**, que é outra
pergunta, e que conversa diretamente com o achado de que o conjunto de teste é o único sem violação
de ficha.

---

## 6. Bloco C — adversariais, contrafactuais e casos-limite

### 6.1 A decisão muda dentro do erro do próprio sensor (D14)

A ficha declara ruído de **±1,0 °C**. Duas leituras que difiram por menos que isso são **fisicamente
indistinguíveis** — o sensor não as separa.

| amplitude | v1 | v2 | v2 / v1 |
|---|---|---|---:|
| **±0,1 °C** (10 % do ruído) | 0,2857 % — **12↑ / 0↓** | 0,4286 % — **10↑ / 8↓** | 1,50× |
| ±0,2 °C | 0,5714 % — 17↑ / 7↓ | 1,0476 % — 25↑ / 19↓ | 1,83× |
| ±0,4 °C | 1,0238 % — 28↑ / 15↓ | 1,2381 % — 29↑ / 23↓ | 1,21× |
| ±1,0 °C (o ruído em cheio) | 1,9524 % — 53↑ / 29↓ | 2,5000 % — 62↑ / 43↓ | 1,28× |

A **±0,1 °C** — um décimo do erro declarado — a v1 já vira **12** decisões e a v2, **18**. No ruído em
cheio, **29 e 43 alarmes somem**. Para a planta: duas leituras que o historiador não consegue
distinguir produzem ordens de manutenção opostas, e qual delas chega é sorteio do erro do sensor.

**A v2 é mais instável em 4 de 4 amplitudes** (1,21× a 1,83×) — o terceiro eixo independente contra a
promoção.

**O par legítimo passa, e é o que dá sentido ao resto:** +15 °C sustentados por 24 h **devem** mudar a
decisão, e mudam — 126 alarmes na v1 e 150 na v2, contra 8 e 1 do ruído de ±0,4 °C nas **mesmas** 600
linhas. O modelo responde à física; o problema é sensibilidade no lugar errado. Sem esse par, um
modelo que ignorasse a temperatura inteira passaria em todos os testes de invariância com nota
máxima.

### 6.2 Contrafactuais — *quais campos entram nessa categoria?*

O guia pergunta literalmente quais campos **não deveriam alterar o estado físico do motor**. Esta é a
resposta, com o critério explícito e o resultado medido ao lado de cada campo testável.

**Critério:** um campo entra na categoria se alterá-lo, mantendo **todas as leituras de sensor
bit-idênticas**, descreve o *mesmo motor no mesmo estado físico*. Campos de sensor ficam de fora por
definição — mudá-los muda o estado. Campos de identificação, escalação e rotulagem entram.

| campo | altera o estado físico? | testado? | resultado medido |
|---|---|---|---|
| `temperatura_c`, `vibracao_rms`, `pressao`, `corrente_a`, `rpm` | **sim** — é a medição | como **par legítimo** | +15 °C/24 h muda 126 (v1) e 150 (v2). **Deve** mudar ✔ |
| `horas_operacao`, `idade_equipamento_meses` | **sim** — estado do ativo | não isoladamente | fora da categoria |
| `id_operador` | **não** — quem está de plantão | sim | **D06:** 0↑/**57**↓ (v1), 0↑/**155**↓ (v2) ✗ |
| `unidade_pressao` | **não** — rótulo de escala; a pressão física é a mesma | sim | **D03:** 5↑/19↓ (v1), 71↑/12↓ (v2) ✗ |
| `turno` | **não** — etiqueta de calendário | sim | **D24:** até 3 (v1) e 10 (v2) decisões ✗ |
| constante de imputação de vibração | **não** — escolha nossa, não do motor | sim | **D04:** 8↑/2↓ (v1), 22↑/7↓ (v2) ✗ |
| `falha_72h` (o rótulo) | **não** — é o gabarito, não entra no serving | sim | **D02:** rever o rótulo muda a predição ✗ |
| `id_maquina` | **não**, mas **saiu da categoria** | sim, e substituído | ver nota abaixo |

> **Por que `id_maquina` saiu.** O desenho original era `test_renomear_o_motor_nao_muda_a_decisao`
> (M02 → M99). Medido: renomear o grupo **inteiro** preserva a média do grupo e **nada muda** — o
> teste passava sem provar nada. Partir o grupo ao meio também não serve: ali `maquina_risco` não se
> move e as 16–20 probabilidades que mudam vêm das **janelas móveis** reiniciando na fronteira, o que
> mede D09, não D02. Foi substituído por `test_revisar_o_rotulo_do_lote_nao_muda_a_predicao`, que
> mexe **só** na coluna de rótulo. É o quarto caso da família "o primeiro desenho não matava a
> hipótese" (§9).

**Cinco campos entram na categoria, e os cinco mudam a decisão.** Nenhum contrafactual passou.

#### D06 e D24 são o mesmo teste com resultados de naturezas diferentes

| | **D06** (`operador_senior`) | **D24** (`turno`) |
|---|---|---|
| taxa de falha do grupo | **0,39881** contra 0,0794 dos outros onze | 0,1600 / 0,1550 / 0,1529 |
| faixa entre grupos | ~32 p.p. | **0,71 p.p.** |
| há confundidor? | **sim, forte** | **não** |
| posição no ranking de sensibilidade | **1ª de 13**, nas duas versões | — |
| leitura | o modelo aprendeu um sinal real, pelo motivo errado | o modelo não tem sinal para aprender |

Em D06 a dependência é **explicável** — errada, mas explicável: o sênior de fato aparece onde há mais
falha, porque é escalado para os motores críticos. Em D24 **não há o que explicar**: `turno` é função
determinística da hora do `timestamp` (0–7 → 1, 8–15 → 2, 16–23 → 3, com **0 de 24** horas ambíguas),
os três turnos falham praticamente igual, e a decisão se move mesmo assim. É sobreajuste a uma coluna
redundante — e é o argumento mais limpo do bloco, porque não exige que ninguém aceite uma tese causal.

### 6.3 Casos-limite

| caso | resultado |
|---|---|
| **painel de um registro** | **perde 3 de 3 alarmes:** as linhas 30, 60 e 90 são `1` no lote e `0` no painel; `maquina_risco` cai de 0,145833/0,187500 para **0,000000** |
| lote de uma linha rotulada | `maquina_risco` vira o próprio rótulo — **1,0**, que é **4,67×** o teto de 0,214286 que o modelo viu no treino |
| lote vazio | devolve `(0, 5)` em silêncio: "sem dado" fica indistinguível de "sem risco" |
| leitura impossível | **500 °C → probabilidade 0,429606**; pressão −3,0 bar → 0,048447. A ficha existe no README e nunca é chamada onde a decisão é tomada |
| leitura duplicada | duplicar a hora 20 move `temp_media_6h` em **+2,029498 °C** na hora 22 — o dobro do ruído do sensor, sem que nenhuma medição nova tenha ocorrido |
| lote de um motor só | passa ✔ |
| lote de valores idênticos | passa ✔ (`delta_temp_24h == 0`, sem exceção) |

O painel de um registro é o caminho mais frágil do sistema, e é o que a sala de controle usa.

---

## 7. O catálogo dos 24 defeitos

Cada um nas quatro partes que o guia exige. O vermelho real de todos está em
[`docs/mapa-defeitos.md`](docs/mapa-defeitos.md).

### D01 ★ — vazamento temporal: `rolling(6, center=True)`

- **Teste que falha:** `test_temp_media_6h_nao_muda_quando_so_o_futuro_muda`
- **Evidência medida:** `temp_media_6h[t=20]` mudou **3,3333 °C** ao perturbar apenas `t+1..t+123`; 29 linhas afetadas. Os dois controles positivos (`temp_max_24h`, `vib_media_6h`) **passam** no mesmo experimento.
- **Causa raiz:** `center=True` faz a janela de 6 ser `[t−2, t+3]`. A feature do instante `t` consome três leituras que só existirão daqui a 3 h.
- **Impacto na planta:** o desempenho medido é **inalcançável em produção**. Em serving a planta não tem `t+3`, então o modelo recebe uma feature sistematicamente diferente da que viu no treino.

### D02 ★ — vazamento de alvo: `maquina_risco` recalculada do rótulo

- **Teste que falha:** `test_maquina_risco_nao_depende_do_rotulo_do_proprio_lote` (+4 oráculos)
- **Evidência medida:** PR-AUC da v1 no teste vai de 0,5811 (sem) para 0,8679 (com) — **+28,68 pp**. `maquina_risco` alcança **0,428571** contra teto de **0,214286** da tabela congelada.
- **Causa raiz:** `_risco_por_maquina` tem um ramo que recalcula o risco como a média de `falha_72h` do grupo quando a coluna está presente. E em `scripts/treinar.py` a intenção de usar a tabela congelada está **morta no código do autor**:
  ```python
  features._RISCO_CONGELADO = None  # força releitura
  X = features.construir(limpo)     # `limpo` ainda tem falha_72h → cai no recálculo
  ```
  A linha seguinte torna a anterior inútil. É a melhor evidência de que D02 é **acidente, não decisão de design**.
- **Impacto na planta:** toda métrica publicada sobre `teste` foi medida com o gabarito dentro da entrada. O número que justificou a promoção da v2 não descreve o sistema que roda.

### D11 ★ — acurácia premia quem não prevê falha; o 0,5 não é o limiar da planta

- **Teste que falha:** `test_recall_da_v2_nao_e_pior_que_o_da_v1`, `test_limiar_de_custo_minimo_e_0_5[v2]`, `test_pr_auc_da_v2_nao_e_pior_que_a_da_v1[producao]`
- **Evidência medida:** IC pareado do Δrecall **[0,206878; 0,270395]**, McNemar `p = 1,1e-47`, **`n01 = 0`**. Promover a v2 herdando o limiar 0,5 custa **4.393** contra **1.765**.
- **Causa raiz:** a decisão de promoção usou acurácia sobre um alvo com prevalência de ~15 %, onde o preditor sempre-zero já acerta **84,40 %**.
- **Impacto na planta:** 157 falhas reais que a v1 pega e a v2 perde. Cada uma é um motor que queima sem aviso.

### D14 ★ — a decisão muda dentro do erro do próprio sensor

- **Teste que falha:** `test_perturbacao_menor_que_o_ruido_do_sensor_nao_muda_a_decisao[0.1|0.2|0.4]`, `test_v2_nao_e_mais_instavel_que_a_v1[amplitude]`
- **Evidência medida:** a ±0,1 °C — 10 % do ruído declarado — **12** decisões na v1 e **18** na v2. No ruído em cheio, 82 e 105. A v2 é mais instável em **4 de 4** amplitudes.
- **Causa raiz:** floresta profunda sem suavização, com cortes densos na faixa de operação da temperatura; nada no sistema conhece a tolerância do sensor.
- **Impacto na planta:** duas leituras fisicamente indistinguíveis geram ordens opostas. A ordem que chega é sorteio do erro de medição.

### D06 ★ — `operador_senior` é escalação reativa, não física do motor

- **Teste que falha:** `test_trocar_o_operador_senior_nao_muda_a_decisao`
- **Evidência medida:** trocar OP-07 por OP-03 em **1.008** leituras, com os sete sensores bit-idênticos, muda **57** decisões na v1 e **155** na v2, **todas para baixo** (`0↑/57↓`, `0↑/155↓`). OP-07 tem taxa de falha **0,39881** contra **0,0794** da média dos outros onze. É a **1ª de 13** features no ranking de sensibilidade, nas duas versões.
- **Causa raiz:** o comentário do SUT entrega — *"o técnico sênior (OP-07) é escalado para os motores mais críticos"*. A feature registra que **alguém já suspeitou da falha**.
- **Impacto na planta:** o modelo funciona exatamente quando não é necessário, e **desaparece no único caso em que a predição valeria algo** — quando ninguém percebeu ainda. Apagar o nome do sênior só faz alarme sumir.

### D24 ★ — `turno` é reetiquetagem do relógio, e mesmo assim decide

- **Teste que falha:** `test_trocar_o_turno_nao_muda_a_decisao[1|2|3]`
- **Evidência medida:** reetiquetar 2.800 leituras sem tocar em sensor muda **3, 1 e 3** decisões na v1 e **8, 10 e 9** na v2. `turno` é função determinística da hora do timestamp (**0 de 24** horas ambíguas). Taxa de falha por turno: 0,1600 / 0,1550 / 0,1529 — faixa de **0,71 p.p.**
- **Causa raiz:** `turno` entra em `ORDEM_FEATURES` como se fosse informação própria, quando é uma bijeção com o bloco de horas que o `timestamp` já carrega. A floresta usa a coluna redundante para separar exemplos que não deveria conseguir separar.
- **Impacto na planta:** a ordem de manutenção depende de como o relógio foi rotulado. A mesma leitura vira alarme ou silêncio conforme a etiqueta que o historiador anexou.

### Os demais 18

| ID | Teste que falha | Evidência medida | Causa raiz | Impacto na planta |
|---|---|---|---|---|
| **D03** | `test_limpar_converte_pressao_de_psi_para_bar` | **32 % do histórico vem em psi** — 1.344 das 4.200 linhas do teste — e entra como se fosse bar; o contrafactual que converte as **2.856** linhas em bar para psi, preservando a pressão física, vira **24** (v1) e **83** (v2) decisões | `unidade_pressao` é normalizada com `.lower()` mas **nunca usada** para converter | 32 % do histórico está numa escala 14,5× maior; o modelo compara maçã com laranja |
| **D04** | `test_vibracao_imputada_fica_na_faixa_fisica_do_sensor` | trocar a constante 0,0 pelo mínimo físico 1,2 mm/s nas **408** ausências vira 10 (v1) e 29 (v2) decisões; **71,50 %** do lote está na janela de influência de algum `0,0` | `fillna(0.0)` imputa um valor **fora** da faixa física 1,2–8,0 | "sensor sem leitura" vira "motor parado e saudável" — o oposto do que o silêncio significa |
| **D05** | `test_limpar_nao_descarta_linhas_silenciosamente` | `limpo[limpo['rpm'] >= 1.0]` descarta linhas sem registro; o corte é em 1,0 rpm e a ficha diz que medição válida começa em 1.650 | filtro silencioso, sem contagem de entrada × saída | o painel mostra **menos motores** do que o historiador mandou, e ninguém é avisado |
| **D07** | `test_prever_registro_respeita_as_chaves_do_dicionario` | **39 de 72** leituras (54,2 %) mudam de decisão só por reordenar as chaves do dicionário | `prever_registro` monta o vetor por `.values()` e **ignora as chaves** | qualquer integração que passe o dicionário em outra ordem recebe predição errada, em silêncio |
| **D08** | `test_delta_temp_24h_compara_com_a_leitura_de_vinte_e_quatro_horas_antes` | após um furo no historiador, `shift(24)` compara com outro instante | `shift(24)` conta **linhas**, não horas | "variação em 24 h" deixa de ser 24 h exatamente quando o dado falha — quando mais importa |
| **D09** | `test_construir_e_estavel_entre_o_lote_inteiro_e_um_recorte` | com recorte **temporal**, 7 das 13 features mudam | `center=True`, `min_periods=1` e `maquina_risco` por lote | reprocessar o mesmo período dá outra resposta: a auditoria não reproduz o alarme |
| **D10** | `test_construir_aceita_indice_duplicado_sem_multiplicar_linhas` | índice com rótulos repetidos multiplica as linhas de saída | `saida.loc[df.index, …]` com rótulos duplicados | um reenvio com índice repetido infla o lote silenciosamente |
| **D12** | `test_ece_fica_abaixo_de_cinco_pontos_percentuais` | Brier v1 0,152340 / v2 0,091652; ECE 19,06 / 5,76 p.p.; **20 de 20 faixas superconfiantes** | floresta profunda sem reponderação; a saída não é probabilidade calibrada | "70 % de risco" não significa 70 %. Priorizar ordens por probabilidade prioriza errado |
| **D13** | `test_nenhuma_coluna_de_sensor_acusa_drift` | a média não acusa **6 de 6**; KS acusa 5; PSI põe 2 em atenção (temperatura 0,1798, vibração 0,1403) | nada no sistema observa a distribuição de entrada | produção já não é o teste, e o sistema não tem como saber |
| **D15** | `test_construir_nomeia_a_coluna_faltante_tambem_para_pressao_e_rpm` / painel de um registro | a validação cobre **4 das 11** colunas que `construir` consome; o painel de um registro **perde 3 de 3 alarmes** | checagem de colunas incompleta; `maquina_risco` degenera em lote de uma linha | a sala de controle vê `0` onde o lote noturno marcou manutenção |
| **D16** | `test_limpar_desduplica_a_chave_id_maquina_timestamp` | duplicar a hora 20 move `temp_media_6h` **+2,029498 °C** na hora 22 | `limpar` não desduplica `(id_maquina, timestamp)` | o reenvio do historiador **dobra o peso** da leitura na janela |
| **D17** | `test_valores_ficam_na_faixa_da_ficha[treino\|producao]` | rpm e pressão fora de faixa em treino (4 e 5) e produção (1 e 1), **zero em teste** | `limpar` não valida **nenhuma** faixa da ficha | o único conjunto limpo é aquele em que a v2 foi medida |
| **D18** | `test_limpar_falha_com_mensagem_que_nomeia_a_coluna[turno\|idade\|id_operador]` | o erro não nomeia a coluna que quebrou | `.astype(int)` sem validação prévia | plantão de madrugada recebe um traceback sem dizer qual coluna veio errada |
| **D19** | `test_limpar_rejeita_unidade_de_pressao_desconhecida` | unidade desconhecida é aceita silenciosamente | só `.lower()`, sem checar o domínio | um `unidade_pressao` digitado errado entra como bar |
| **D20** | `test_temperatura_ausente_nao_e_silenciosamente_imputada` | o NaN é ignorado e a janela devolve número confiante | `min_periods=1` | buraco de sensor vira leitura confiante, sem marca de que faltou dado |
| **D21** | `test_leitura_fisicamente_impossivel_e_rejeitada` | **500 °C → probabilidade 0,429606**; pressão −3,0 bar → 0,048447 | `_matriz` só checa forma e finitude; nenhuma validação no ponto de serving | o sistema responde com seis casas decimais a uma leitura que não existe fisicamente |
| **D22** | `test_limpar_preserva_rastreabilidade_da_linha_original` | o índice reconstruído não permite auditar quais leituras foram ignoradas | `reset_index(drop=True)` | com D05 ativo, não há como auditar o que foi descartado |
| **D23** | `test_artefatos_batem_com_o_manifest` | 4 divergências de sha256 (os três CSVs e `risco_maquina.json`); os dois artefatos de modelo batem | o manifest não foi regravado depois de os dados serem reescritos | a **única** verificação de integridade que o SUT oferece acusa erro no estado de fábrica, e fica inutilizável para distinguir corrupção real |

> **D23 é bookkeeping, não artefato obsoleto — e isso foi medido, não suposto.** Os limiares dos
> 1.260 nós que testam `maquina_risco` casam **bit a bit** com `round(ponto_médio, 6)` dos valores de
> **hoje** (400/400 na v1, 860/860 na v2). Por acaso seria impossível: ~2,85e-04 de chance por
> limiar. **Dados, tabela de risco e modelos formam um conjunto coerente.**

---

## 8. Os testes que passam também são resultado

**170 testes passam.** Uma suíte só vermelha não distingue sinal de ruído, e parte do Sentinela está
correta:

- `construir` **devolve as 13 features na ordem canônica** e preserva a ordem de entrada sob
  embaralhamento.
- As janelas móveis **não atravessam motores** — cada uma é calculada dentro do seu `id_maquina`.
- `limpar` **não muta o quadro de entrada** e é idempotente.
- `operador_senior` marca **só** OP-07, como documentado.
- `risco_maquina.json` cobre **M01..M25**, sem motor faltando.
- O modelo **não é preditor constante** e responde à física: +15 °C por 24 h levantam 126 e 150
  alarmes.
- `modelo.carregar` **valida a sincronia** entre `ordem_features` do artefato e
  `features.ORDEM_FEATURES`, e rejeita versão desconhecida.
- Seis propriedades com `hypothesis` passam com **0 casos inválidos** — nenhuma satisfeita a vazio.

---

## 9. Seis oráculos que não matavam a hipótese

O enunciado paga por "formular uma hipótese e desenhar o teste que a mata". Em **seis** casos o
primeiro desenho **não matava** — e todos têm a mesma forma: o oráculo mede com a ferramenta errada e
conclui o contrário. **Um teste de defeito que passa é pior que teste nenhum**, porque dá a impressão
de que a costura foi verificada.

| defeito | primeiro desenho | por que falhava em acusar | desenho que funciona |
|---|---|---|---|
| **D07** | comparar a decisão de **uma** linha | coincidem em ~46 % dos casos | varrer o lote e reportar a taxa (54,2 %) |
| **D09** | recortar **por motor** | as janelas já são por motor | recorte **temporal**, como a planta reprocessa |
| **D22** | sem descartar linha | o índice reconstruído coincide por acidente | **criar** a condição (descartar uma linha) |
| **D02** | renomear o motor / assertar **decisão** | renomear preserva a média do grupo; o limiar de 0,5 engole a evidência | mexer só no rótulo e assertar **probabilidade** |
| **McNemar** | calcular sobre o lote inteiro | responde sobre **acurácia** e aponta a v2 | restringir aos positivos reais, onde o recall é definido |
| **D04** | apagar uma leitura e assertar a decisão | move 2,09 °C na feature mas só 0,0239 na probabilidade; **0** decisões viram | trocar a **constante de imputação** (0,0 → 1,2 mm/s) |

A lição que atravessa os seis: **a decisão é a variável que a planta consome, mas a evidência do
defeito aparece antes dela.** Em D02, a violação começa com **2** rótulos revistos e a primeira
decisão só vira com **21** — assertar decisão exigiria uma perturbação 10× maior para acusar o mesmo
defeito.

Um sétimo caso, do instrumento e não do oráculo: o primeiro ranking de sensibilidade devolveu
`operador_senior` com `delta_medio = 0,000000`, em **último** lugar — enquanto o contrafactual de D06
virava 155 decisões com ela. A feature é binária, e ruído de ±0,43 em torno de 0 ou 1 nunca cruza o
corte em 0,5. **O instrumento estava cego exatamente à feature que interessava.** Corrigido (binária
é invertida, contínua leva ±1 desvio), ela sobe a 1ª de 13.

### Uma previsão nossa que não se confirmou

Prevíamos que `maquina_risco` estaria entre as features mais influentes do ranking de perturbação.
**Não está** — 6ª na v1 e 7ª na v2, de 13. O assert cobre só `operador_senior`; cravar "metade
superior" seria ajustar a régua depois de ver o resultado. O dano de `maquina_risco` está provado por
caminho mais forte: o vazamento de alvo (D02) e a degeneração em lote de uma linha (D15).

---

## 10. Ancoragem no material da disciplina

Levantamento por varredura dos seis consolidados **e** dos seis notebooks das aulas. Dos **16 itens**
exigidos pelos três blocos obrigatórios, **12 têm método de aula** (sete com a assinatura literal) e
**4 não têm base em nenhuma aula**.

| Item | Aula | O que usamos | Veredito |
|---|---|---|---|
| Tipos, faltantes, faixas, unicidade, completude | 3 | `ficha.validar_*`, no padrão `raise ValueError` / `return True` | aula |
| Unidades | 3 | `FATOR_PSI_POR_BAR`, teste metamórfico — o caso do Mars Climate Orbiter com outra grandeza | aula |
| Ordem das linhas | 2 | embaralhar e comparar linha a linha | aula |
| Feature de `t` usa só até `t` | 2 | propriedade **metamórfica** aplicada ao eixo tempo | aula\* |
| Property-based | 2 | `@given`, `max_examples=50`, `--hypothesis-show-statistics` | aula |
| Bootstrap pareado | 4 | `bootstrap_ci` / `bootstrap_ci_pareado`, mesmos índices, regra `lo>0`/`hi<0` | aula |
| Distribuições teste × produção | 6 | `detectar_drift_media`, `detectar_drift_ks`, `psi` — as três assinaturas da aula | aula |
| Estabilidade do veredito | 4 | 200 sementes, exigindo ≥ 199/200 | aula |
| Invariância adversarial + par legítimo | 4 | perturbação numérica com o rótulo esperado declarado | aula |
| Casos-limite | 1, 6 | 7 testes de limite | aula |
| **McNemar** | — | `scipy.stats.binomtest` sobre os discordantes | **FORA** |
| **Métricas de classe rara** | 6 | `average_precision`, `fbeta(β=2)`, `recall_com_precisao_minima` | **FORA** |
| **Escolha de limiar** | 6 | varredura 0,05–0,95 com custo assimétrico | **FORA** |
| **Calibração** | — | `brier`, `ece`, curva de confiabilidade | **FORA** |

**A fronteira, declarada explicitamente:** McNemar não aparece em nenhum consolidado nem notebook.
Métricas de classe rara e escolha de limiar aparecem **só como conceito**, no trecho que a própria
aula 6 declara *"fora da ementa e sem cobrança em avaliação"*. Calibração não aparece em lugar
nenhum. Os quatro são **exigidos pelo enunciado**, e foram implementados com **numpy e `scipy`** em
vez de trazer `scikit-learn`, que nenhuma aula usou. O guia autoriza: *"ferramentas externas (…
Hypothesis, scipy) são bem-vindas, não obrigatórias"*.

Também fora das aulas, no ferramental: `xfail(strict=True)`, `conftest.py`, `--strict-markers`,
`junitxml` e Docker. As aulas documentavam defeito com um teste que **passa** afirmando o
comportamento errado; escolhemos o `xfail` estrito porque ele avisa quando o defeito é corrigido.

---

## 11. Anexo: os patches, e o que eles revelam

> **Esta seção está fora do que o enunciado pede.** Ele pede os três blocos, as instruções, o log e
> ao menos uma falha documentada — e manda **não editar o pacote**. Nenhuma conclusão dos §§1 a 10
> depende do que está aqui: os 231 testes rodam contra o clone intacto. O anexo existe porque, com
> os defeitos já provados por teste que falha, a pergunta *"e se corrigíssemos?"* teve uma resposta
> que contraria o que prevíamos, e isso valia registrar.

Três patches de mudança mínima, em [`patches/`](patches/), aplicados com `git apply` a um clone
**descartável dentro do container**, revertido e conferido ao fim por
[`scripts/correcoes.sh`](scripts/correcoes.sh) — o pacote sob teste não é alterado de forma
persistente e este repositório nunca o contém:

| Patch | Corrige | O que muda |
|---|---|---|
| `D01-vazamento-temporal.patch` | D01 | remove `center=True` de `temp_media_6h`. **Não** toca `min_periods=1`: mexer nele introduziria NaN e `_matriz` levantaria `ValueError` |
| `D02-vazamento-alvo.patch` | D02 | remove o ramo de `_risco_por_maquina` que recalcula o risco do rótulo |
| `D03-unidade-de-pressao.patch` | D03, e absorve D19 | converte psi → bar em `limpar` e **rejeita** unidade fora do domínio |

**Os quatro testes-alvo passam depois dos patches**, e o número de testes de defeito que ainda
falham cai de **61** para **47** (14 passam a passar). O manifest continua exatamente nas 4
divergências de D23 — os patches mexem em `src/`, e o manifest cobre `dados/` e `artefatos/`.

### A tabela antes/depois — e o resultado não é o que prevíamos

Conjunto teste, sem vazamento, limiar 0,5, `custo = 20×FN + FP`. Saída real de `make correcoes`,
em [`evidencias/log-correcoes.txt`](evidencias/log-correcoes.txt):

| versão | métrica | antes | depois | Δ |
|---|---|---:|---:|---:|
| v1 | recall | 0,937405 | 0,934351 | −0,003053 |
| v1 | precisão | 0,393842 | 0,392811 | −0,001031 |
| v1 | F2 | 0,734626 | 0,732408 | −0,002218 |
| v1 | **PR-AUC** | 0,581091 | **0,605164** | **+0,024073** |
| v1 | **custo** | **1.765** | **1.806** | **+41** |
| v2 | recall | 0,697710 | 0,697710 | 0,000000 |
| v2 | precisão | 0,513483 | 0,536385 | +0,022902 |
| v2 | F2 | 0,650997 | 0,658122 | +0,007125 |
| v2 | **PR-AUC** | 0,671808 | **0,696078** | **+0,024270** |
| v2 | custo | 4.393 | 4.355 | −38 |

**Prevíamos que os patches derrubassem as métricas. O que aconteceu é mais interessante, e é
melhor para o argumento.**

**A PR-AUC melhora nas duas versões** — +2,41 pp na v1 e +2,43 pp na v2. Com a entrada honesta, os
modelos **ranqueiam melhor**: a capacidade de ordenar motores por risco, que é o que a PR-AUC mede,
aumenta quando se tira o vazamento e se corrige a unidade.

**E a decisão no limiar 0,5 piora para a v1** — custo de 1.765 para 1.806, recall de 0,9374 para
0,9344. Não é contradição: **o 0,5 estava afinado para a entrada defeituosa.** Tirar o defeito move
a distribuição das probabilidades, e o corte que era ótimo deixa de ser.

É exatamente o argumento do D11, chegando por outro caminho: **o limiar é parte do modelo, não uma
constante.** Quem corrigir os defeitos e mantiver o 0,5 vai concluir que "a correção piorou o
sistema" — e vai estar lendo o número errado de novo.

**O que isso confirma sobre o retreino.** Os artefatos foram treinados **com** os defeitos
presentes: a floresta aprendeu a usar `maquina_risco` inflada pelo rótulo e a pressão em duas
escalas. Corrigir a entrada sem retreinar entrega ao modelo uma distribuição que ele nunca viu — e o
efeito medido é o esperado disso: o sinal melhora, e o ponto de corte herdado deixa de servir.

---

## 12. Conclusão: corrigir exige retreinar, e retreinar exige antes esta suíte

O Sentinela tem **24 defeitos catalogados**, e os dois centrais são vazamentos: o **temporal** (D01),
que faz a feature de agora usar leitura do futuro, e o de **alvo** (D02), que põe o gabarito dentro da
entrada. Juntos, eles significam que **nenhuma métrica já publicada sobre este sistema descreve o
sistema.**

A promoção da v2 não se sustenta — não por uma diferença mal lida, mas porque foi decidida pelo
instrumento errado. No ponto de operação a v2 é **estritamente dominada** (`n01 = 0`), e em **nenhum**
dos 19 pontos de limiar ela domina a v1. Reajustá-la não resolve.

**E o limiar é parte do modelo, não uma constante** — é o que D11 estabelece, e ele vem inteiro do
Bloco B (§5.1 e §5.2), sem depender de corrigir nada. O `0,5` não é o ponto de operação da planta:
com prevalência de ~15 % e FN vinte vezes mais caro que FP, ele foi herdado, não escolhido. Em
**nenhum** dos 19 pontos de limiar varridos a v2 domina a v1, e no ponto herdado promover a v2 custa
**4.393** contra **1.765**.

A consequência é direta: **mexer na entrada sem revisar o limiar, e sem retreinar, não é correção.**
Os artefatos foram treinados **com** os defeitos presentes — a floresta aprendeu a usar
`maquina_risco` inflada pelo rótulo e a pressão em duas escalas. Tirar o defeito da entrada entrega
ao modelo uma distribuição que ele nunca viu, e move a distribuição das probabilidades sob um ponto
de corte que ficou onde estava. Quem fizer isso mantendo o `0,5` vai concluir que "a correção piorou
o sistema" — e vai estar lendo o número errado pela terceira vez.

O anexo §11 mediu exatamente isso e serve de corroboração, não de fundamento: com a entrada honesta
a PR-AUC **sobe** nas duas versões (+2,41 pp e +2,43 pp), e o custo da v1 **piora** (1.765 → 1.806).
O sinal melhora e o ponto de corte herdado deixa de servir — que é a previsão de D11, confirmada.

Daí a conclusão operacional, e é ela que a Nortemec precisa ouvir:

> **Corrigir o código exige retreinar o modelo. E retreinar exige, antes, esta suíte** — porque sem
> ela não há como saber se o modelo novo é melhor que o velho. A pergunta "a v2 é melhor que a v1?"
> não tinha resposta confiável neste repositório até agora, e é exatamente a pergunta que vai voltar
> no dia seguinte ao retreino.

Quatro defeitos ficam **documentados e não corrigidos, deliberadamente** — D06, D14, D21 e D24 —
porque corrigi-los exige retreinar ou alterar o pacote sob teste, o que o enunciado proíbe. D23, o
manifest desatualizado, fica pelo mesmo motivo: regerá-lo alteraria o SUT.

---

## Anexos

- [`README.md`](README.md) — como rodar, estrutura, o log verde colado
- [`docs/mapa-defeitos.md`](docs/mapa-defeitos.md) — o vermelho real de cada um dos 24
- [`docs/decisoes.md`](docs/decisoes.md) — as decisões de execução e as armadilhas encontradas
- [`evidencias/log-suite.txt`](evidencias/log-suite.txt) — `170 passed, 61 xfailed`, exit 0
- [`evidencias/log-defeitos.txt`](evidencias/log-defeitos.txt) — `61 failed`, exit 1
- [`evidencias/log-correcoes.txt`](evidencias/log-correcoes.txt) — os 3 patches e a tabela antes/depois (anexo §11, fora do escopo do enunciado)
- [`patches/`](patches/) — as três correções propostas, com o `README.md` que explica a ordem
- [`evidencias/linha-de-base.md`](evidencias/linha-de-base.md) — as 12 linhas e as três perguntas
- [`evidencias/medicoes.json`](evidencias/medicoes.json) — toda taxa medida, em JSON
- [`evidencias/junit-suite.xml`](evidencias/junit-suite.xml) · [`evidencias/junit-defeitos.xml`](evidencias/junit-defeitos.xml)
