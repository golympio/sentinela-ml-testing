# Linha de base

Gerado por `scripts/linha_de_base.py`. **Nenhum número entra em assert nas fases 4 e 5
sem ter passado por esta tabela.**

- SUT: `c9020d7ba3bb4e6fd4ae22d46346a787b16adc02`
- `SUITE_SEED`: `42`
- versões: `numpy=2.5.3`, `pandas=2.3.3`, `pytest=9.1.1`, `scipy=1.18.1`

> ### Convenção de sinal — leia antes de citar qualquer Δ
>
> Este arquivo usa **v2 − v1** nas tabelas descritivas, porque "a v2 ganhou +3,5 pp"
> é como a Nortemec fala e é a frase que o trabalho contesta. O **intervalo de
> confiança pareado** do HANDOFF 04 usa a convenção oposta, **v1 − v2**, fixada pelo
> SPEC §5: `lo > 0` ⇒ v1 melhor, `hi < 0` ⇒ v2 melhor.
>
> São o mesmo fato com o sinal trocado. Por isso **nenhuma coluna aqui se chama
> "Δ"**: cada uma carrega a fórmula no próprio nome.


> **`com vazamento`** = como o SUT faz hoje (o rótulo fica no quadro e
> `maquina_risco` é recalculada com ele). **`sem vazamento`** = simulação do serving,
> com a coluna de rótulo removida antes de construir as features. A simulação é
> declarada como tal: em produção o rótulo não existe porque a falha ainda não
> aconteceu.

## Contexto dos conjuntos

| conjunto | linhas | prevalência | acurácia do preditor sempre-zero |
|---|---:|---:|---:|
| treino | 16800 | 0.1154 | 0.8846 |
| teste | 4200 | 0.1560 | 0.8440 |
| producao | 4200 | 0.1426 | 0.8574 |

## As 12 linhas

| conjunto | versão | vazamento | acurácia | precisão | recall | F1 | F2 | PR-AUC | Brier | ECE |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| treino | v1 | com | 0.9196 | 0.5899 | 0.9948 | 0.7406 | 0.8748 | 0.9413 | 0.0517 | 0.1084 |
| treino | v1 | sem | 0.9196 | 0.5899 | 0.9948 | 0.7406 | 0.8748 | 0.9413 | 0.0517 | 0.1084 |
| treino | v2 | com | 0.9857 | 0.9748 | 0.8994 | 0.9356 | 0.9136 | 0.9914 | 0.0162 | 0.0460 |
| treino | v2 | sem | 0.9857 | 0.9748 | 0.8994 | 0.9356 | 0.9136 | 0.9914 | 0.0162 | 0.0460 |
| teste | v1 | com | 0.8860 | 0.5832 | 0.9420 | 0.7204 | 0.8388 | 0.8679 | 0.0863 | 0.1355 |
| teste | v1 | sem | 0.7652 | 0.3938 | 0.9374 | 0.5547 | 0.7346 | 0.5811 | 0.1523 | 0.1906 |
| teste | v2 | com | 0.9207 | 0.7164 | 0.8137 | 0.7620 | 0.7922 | 0.8117 | 0.0685 | 0.0716 |
| teste | v2 | sem | 0.8498 | 0.5135 | 0.6977 | 0.5916 | 0.6510 | 0.6718 | 0.0917 | 0.0576 |
| producao | v1 | com | 0.8581 | 0.5013 | 0.9800 | 0.6633 | 0.8228 | 0.7728 | 0.0935 | 0.1400 |
| producao | v1 | sem | 0.8174 | 0.4354 | 0.9449 | 0.5961 | 0.7657 | 0.6433 | 0.1259 | 0.1693 |
| producao | v2 | com | 0.8660 | 0.5186 | 0.8381 | 0.6407 | 0.7461 | 0.7198 | 0.0820 | 0.0823 |
| producao | v2 | sem | 0.8569 | 0.4989 | 0.7713 | 0.6059 | 0.6954 | 0.6379 | 0.0877 | 0.0717 |

## As três perguntas

### (a) Os +3,5 pp de acurácia da v2 reproduzem?

O README do SUT afirma que a v2 "ganhou +3,5 pontos percentuais de acurácia no
conjunto de teste". A equipe mediu do jeito que o SUT roda — isto é, **com vazamento**.

| conjunto | modo | acurácia v1 | acurácia v2 | acurácia(v2) − acurácia(v1), pp |
|---|---|---:|---:|---:|
| treino | com | 0.9196 | 0.9857 | +6.61 |
| treino | sem | 0.9196 | 0.9857 | +6.61 |
| teste | com | 0.8860 | 0.9207 | +3.48 |
| teste | sem | 0.7652 | 0.8498 | +8.45 |
| producao | com | 0.8581 | 0.8660 | +0.79 |
| producao | sem | 0.8174 | 0.8569 | +3.95 |

**Resposta:** no conjunto de teste, com vazamento, o Δ medido é **+3.48 pp**.

### (b) De quanto é o Δrecall entre v1 e v2?

| conjunto | modo | recall v1 | recall v2 | recall(v2) − recall(v1), pp | F2 v1 | F2 v2 |
|---|---|---:|---:|---:|---:|---:|
| treino | com | 0.9948 | 0.8994 | -9.54 | 0.8748 | 0.9136 |
| treino | sem | 0.9948 | 0.8994 | -9.54 | 0.8748 | 0.9136 |
| teste | com | 0.9420 | 0.8137 | -12.82 | 0.8388 | 0.7922 |
| teste | sem | 0.9374 | 0.6977 | -23.97 | 0.7346 | 0.6510 |
| producao | com | 0.9800 | 0.8381 | -14.19 | 0.8228 | 0.7461 |
| producao | sem | 0.9449 | 0.7713 | -17.36 | 0.7657 | 0.6954 |

### (c) De quanto é a inflação causada pelo vazamento?

Diferença `com` − `sem`, na mesma linha de conjunto e versão.

| conjunto | versão | recall(com) − recall(sem), pp | F2, idem | PR-AUC, idem | acurácia, idem |
|---|---|---:|---:|---:|---:|
| treino | v1 | +0.00 | +0.00 | +0.00 | +0.00 |
| treino | v2 | +0.00 | +0.00 | +0.00 | +0.00 |
| teste | v1 | +0.46 | +10.41 | +28.68 | +12.07 |
| teste | v2 | +11.60 | +14.12 | +13.99 | +7.10 |
| producao | v1 | +3.51 | +5.71 | +12.95 | +4.07 |
| producao | v2 | +6.68 | +5.08 | +8.20 | +0.90 |

## Curva de confiabilidade (teste, sem vazamento)

O que o modelo prometeu (`confiança`) contra o que aconteceu (`observado`), faixa a
faixa. `gap` positivo = **superconfiança**: o painel anuncia mais risco do que existe.

| faixa | n (v1) | confiança v1 | observado v1 | gap v1 | n (v2) | confiança v2 | observado v2 | gap v2 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.0–0.1 | 1780 | 0.0321 | 0.0169 | +0.0152 | 2449 | 0.0154 | 0.0139 | +0.0015 |
| 0.1–0.2 | 314 | 0.1434 | 0.0096 | +0.1339 | 283 | 0.1450 | 0.0636 | +0.0814 |
| 0.2–0.3 | 225 | 0.2472 | 0.0000 | +0.2472 | 190 | 0.2467 | 0.1895 | +0.0572 |
| 0.3–0.4 | 160 | 0.3582 | 0.0250 | +0.3332 | 177 | 0.3451 | 0.2599 | +0.0852 |
| 0.4–0.5 | 162 | 0.4473 | 0.0247 | +0.4227 | 211 | 0.4592 | 0.3033 | +0.1559 |
| 0.5–0.6 | 219 | 0.5577 | 0.2055 | +0.3522 | 220 | 0.5454 | 0.2864 | +0.2590 |
| 0.6–0.7 | 394 | 0.6504 | 0.2589 | +0.3915 | 278 | 0.6486 | 0.3345 | +0.3140 |
| 0.7–0.8 | 332 | 0.7573 | 0.3464 | +0.4109 | 222 | 0.7486 | 0.7027 | +0.0459 |
| 0.8–0.9 | 367 | 0.8405 | 0.5232 | +0.3174 | 137 | 0.8414 | 0.8321 | +0.0092 |
| 0.9–1.0 | 247 | 0.9305 | 0.6478 | +0.2827 | 33 | 0.9513 | 0.9394 | +0.0119 |

**20 de 20 faixas têm `gap` positivo**: as duas versões são
superconfiantes em toda a escala — nunca prometem de menos. É o defeito **D12**.

## Leitura

**(a) Sim, os +3,5 pp reproduzem** — +3.48 pp no conjunto de teste, no
modo em que a equipe mediu. O gate de escalonamento **não** dispara: a afirmação do
README é verdadeira como afirmação de acurácia. O problema não é o número, é a métrica.

**(b) A v2 compra acurácia com recall.** No teste, o recall cai de
0.9420 para 0.8137 — **-12.82 pp** —
e sem vazamento a queda é de -23.97 pp. O Δrecall é
**negativo nos três conjuntos e nos dois modos** (na convenção v2 − v1 deste
arquivo). Com prevalência de ~15 %, o preditor
sempre-zero já acerta 84 % no teste: acurácia é quase insensível à classe que importa.
F2, que pesa recall 4×, também piora com a v2 no teste e em produção. Promover a v2
troca motores queimados por um número de slide — é o defeito **D11**.

**(c) O vazamento infla tudo, exceto no treino.** No treino a inflação é **exatamente
0,00 pp** em todas as métricas: a tabela congelada `risco_maquina.json` **é** a média por
motor do próprio treino, então recalcular a partir do rótulo devolve o mesmo valor. A
diferença na feature existe (máx. 4,762e-07, o arredondamento a 6 casas do arquivo) mas
não muda uma única probabilidade — elas são bit-idênticas.

Fora do treino a inflação é grande: no teste, a PR-AUC da v1 vai de 0.5811
para 0.8679 (**+28.68 pp**) e a acurácia sobe
+12,07 pp. O mecanismo é visível na própria feature: com vazamento `maquina_risco`
alcança **0,428571** em teste e produção, contra um teto de **0,214286** na tabela
congelada — o valor recalculado sai da faixa que o modelo viu no treino.

> **Consequência para as fases 4 e 5:** toda comparação v1 × v2 tem de ser lida **sem
> vazamento**, porque é esse o número que a planta obtém. E nenhuma delas pode se apoiar
> em acurácia.

