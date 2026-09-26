# Mapa de defeitos — vermelho medido

Um defeito só entra aqui **depois** de ter sido visto falhar sem marker. A saída colada
é real, copiada da execução; nunca uma paráfrase. Só então o teste recebe
`@pytest.mark.defeito` + `@pytest.mark.xfail(strict=True, reason="D<nn> — …")`.

Mapa completo de causa → impacto → teste: SPEC §4.3. Aqui fica a **evidência**.

---

## D02 ★ — vazamento de alvo: `maquina_risco` recalculada a partir do rótulo

**Onde:** `tests/test_vazamento_alvo.py` · **Medido em:** 20260924, HANDOFF 03 Etapa 4
É o defeito que derruba a promoção da v2.

`features._risco_por_maquina` faz `df.groupby("id_maquina")["falha_72h"].transform("mean")`
sempre que a coluna de rótulo está presente. Como o alvo vem no CSV dos três conjuntos
(SPEC P8), **toda métrica publicada sobre o Sentinela foi medida com o gabarito dentro da
entrada**.

### Vermelho, antes de qualquer marker

```
5 failed (7 ids), 1 passed

3217 de 4200 probabilidades mudam ao remover a coluna `falha_72h`; |Δ| máximo = 0.5767
`maquina_risco` difere em 4200 de 4200 linhas; |Δ| máximo = 0.415178
1512 de 4200 linhas têm `maquina_risco` acima do teto da tabela congelada (0.214286);
    máximo observado = 0.428571
v1: rever 21 de 168 rótulos de M02, sem tocar em nenhum sensor, mudou 168 de 4200
    probabilidades; |Δ| máximo = 0.244217
v2: idem, 168 de 4200; |Δ| máximo = 0.080209
v1: o vazamento infla Δrecall=+0.46 pp, ΔF2=+10.41 pp, ΔPR-AUC=+28.68 pp
v2: o vazamento infla Δrecall=+11.60 pp, ΔF2=+14.12 pp, ΔPR-AUC=+13.99 pp
```

### Não é hipotético: é como o modelo foi treinado

`scripts/treinar.py` chama `features.construir(limpo)` com o rótulo ainda no quadro, e a linha
imediatamente anterior — `features._RISCO_CONGELADO = None  # força releitura` — existe só para
usar a tabela congelada que o passo seguinte torna inalcançável. Ver `docs/decisoes.md`,
"D02: a intenção morta no `treinar.py`".

### O mecanismo, visível na própria feature

Com vazamento, `maquina_risco` alcança **0,428571** em teste e produção — exatamente o dobro do
teto de **0,214286** da tabela congelada. O valor recalculado sai da faixa que o modelo viu no
treino: extrapolação silenciosa no ponto de serving.

### Duas armadilhas de oráculo, medidas

Ambas fizeram um teste de defeito **passar** antes de serem corrigidas.

1. **Renomear o motor não é experimento de D02.** `maquina_risco` é a média **do grupo**:
   renomear o grupo inteiro (M02 → M99) preserva a média e nada muda. Partir o grupo ao meio
   também não serve — ali `maquina_risco` não se move (as duas metades de M02 têm a mesma média)
   e as 16–20 probabilidades que mudam vêm de as **janelas móveis** reiniciarem na fronteira, o
   que mede D09. Só mexer na coluna de rótulo isola o mecanismo.

2. **Assertar decisão binária esconde o defeito numa faixa larga.** Revisando rótulos de M02:

   | rótulos revistos | média de M02 | probabilidades que mudam (v1) | decisões que viram (v1) |
   |---:|---:|---:|---:|
   | 1 | 0,005952 | 0 | 0 |
   | 2 | 0,011905 | 3 | 0 |
   | 8 | 0,047619 | 128 | 0 |
   | 13 | 0,077381 | 141 | 0 |
   | 21 | 0,125000 | 168 | **1** |
   | 34 | 0,202381 | 168 | 4 |

   A violação começa em **2** rótulos; a primeira decisão só vira com **21**. Um oráculo de
   decisão daria o defeito por inexistente em todo o intervalo entre os dois. É a mesma lição de
   D07, D09 e D22 no Bloco A.

**Patch:** **sim** (D02). A queda de métrica após o patch é esperada e está explicada no relatório
— é a diferença entre o desempenho medido e o alcançável.

---

## D23 — o manifest do SUT está desatualizado no commit pinado

**Onde:** `tests/test_reprodutibilidade.py` · **Medido em:** 20260924, HANDOFF 01 Etapa 5
Defeito **novo**, fora da lista D01–D22 levantada na leitura do fonte: só aparece ao rodar.

`verificar_manifest()` é a única verificação de integridade que o SUT oferece, e o README dele
promete `[]`. No commit pinado ela acusa quatro divergências **no estado de fábrica** — então
ninguém consegue usá-la para distinguir corrupção real de ruído de origem.

### O vermelho (de `make defeitos`, com `--runxfail`)

```
def test_artefatos_batem_com_o_manifest():
>       assert sn.artefatos.verificar_manifest() == []
E       AssertionError: assert ['sha256 dife...maquina.json'] == []
E         Left contains 4 more items, first extra item: 'sha256 diferente: dados/treino.csv'
```

### Quais arquivos divergem

| arquivo do manifest | sha256 |
|---|---|
| `dados/treino.csv` | **diverge** |
| `dados/teste.csv` | **diverge** |
| `dados/producao.csv` | **diverge** |
| `artefatos/risco_maquina.json` | **diverge** |
| `artefatos/modelo_v1.json` | bate |
| `artefatos/modelo_v2.json` | bate |

Os dois modelos baterem é o que separa D23 de um clone corrompido: a corrupção não escolheria
poupar exatamente os dois artefatos que não foram regerados.

### As três evidências de que o dado é que mudou, não o manifest

1. **Cronologia.** `manifest.json` tem `gerado_em: 2026-09-08T08:19:45`; o repositório tem um
   commit único, `c9020d7`, datado de `2026-09-10 22:52:31 -0300`. O manifest foi gerado dois
   dias **antes** do conteúdo que ele deveria descrever ser publicado.
2. **Clone limpo.** `git status --porcelain` dentro do container devolve vazio com exit 0
   (V11): nada no nosso lado tocou o SUT.
3. **`risco_maquina.json` e `dados/treino.csv` são um par coerente — os modelos é que não são.**
   A tabela cobre os 25 motores e é numericamente consistente com o treino publicado: os **25 de
   25** valores são **exatamente `round(média_por_motor, 6)`**, que é a precisão em que o arquivo
   foi gravado. A média da tabela (`0.115417`) é idêntica à prevalência global do treino.

   ```
   M01 no JSON: 0.108631  | real: 0.10863095238095238
   iguais a round(real, 6): 25 de 25
   maior |delta|: M16 = 4.762e-07
   ```

   Ou seja: **dados e tabela de risco são um par coerente**, e os quatro arquivos que divergem no
   manifest divergem **juntos**.

   > **Os modelos também são coerentes com esses dados — medido, não suposto.** A suspeita
   > inicial era que os modelos, que ainda batem com o manifest, tivessem sido treinados sobre a
   > geração anterior dos dados. A medição dos limiares diz que não. `treinar.py` linha 58 grava
   > `round(float(v), 6)`, logo o limiar publicado é `round(ponto_médio_pleno, 6)` — e é isso que
   > se mede, **bit a bit**: **400 de 400** nós de `maquina_risco` na v1 e **860 de 860** na v2
   > são idênticos a `round(ponto_médio, 6)` dos valores de **hoje**; nenhum fora da faixa.
   > Cortes de árvore são a impressão digital do conjunto de valores usado no treino, então eles
   > **só poderiam ter sido aprendidos sobre exatamente estes dados**. Método, números e a
   > distinção entre as duas distâncias máximas (4,76e-07 e 5,00e-07, referências diferentes) em
   > `docs/decisoes.md`.

   > **Armadilha de medição, registrada porque quase entrou no relatório.** Comparando com `==`,
   > só 2 dos 25 "batem" — M11 e M17, que são exatamente `0.0`. Não é inconsistência: é float de
   > precisão plena contra um decimal arredondado a 6 casas. A primeira versão desta seção
   > afirmava "2 de 25" e com isso a leitura de D23 virava "a tabela está inconsistente com os
   > dados", que é o contrário do que a evidência diz. É o mesmo cuidado que a suíte já aplica nos
   > testes numéricos com `assert_allclose`/`pytest.approx`, e que faltou aqui.

### Consequências

- **Para a suíte:** o teste da invariante é `xfail(strict=True)`; um segundo teste, **verde**,
  trava a divergência no conjunto exato conhecido (`DIVERGENCIAS_CONHECIDAS`, em
  `scripts/smoke.py`). O smoke do build aborta se aparecer uma quinta divergência ou se uma
  das quatro sumir.
- **Para o HANDOFF 03:** o gate dos +3,5 pp começa **sem** explicação alternativa pendurada.
  Dados, tabela de risco e modelos são um conjunto coerente, então se os +3,5 pp não reproduzirem,
  a hipótese "artefato obsoleto" já está descartada neste eixo e a causa terá de ser outra.
- **Ponta solta para o HANDOFF 04:** a v2 tem **2** limiares a menos de 5e-7 de um valor da
  tabela. O treino usa `maquina_risco` em precisão plena (o `treinar.py` chama `construir` com o
  rótulo, caindo no recálculo por lote — o próprio D02) e o serviço sem rótulo usa a tabela
  arredondada a 6 casas. Nesses 2 nós o arredondamento pode mandar a linha para o lado oposto da
  árvore: descasamento treino/serviço real e minúsculo, com taxa de flip mensurável.

**Patch:** **não**. Regerar o manifest reescreveria `artefatos/manifest.json` dentro do SUT,
violando C12 (o nosso repositório não altera o pacote sob teste) e derrubando V11. D23 fica
documentado como defeito observado, não corrigido — e a medição dos limiares o classifica como
defeito de **bookkeeping e procedência** (o manifest não foi regravado), não como artefato obsoleto.

---

## D17 — `limpar` não valida nenhuma faixa da ficha técnica

**Onde:** `tests/test_contrato_dados.py`
**Testes:** `test_rpm_esta_na_faixa_da_ficha`, `test_pressao_convertida_esta_na_faixa_da_ficha`
**Medido em:** 20260924, HANDOFF 02 Etapa 3

Vermelho, antes de qualquer marker:

```
ValueError: rpm: 4 de 16800 leituras fora da faixa [1650.0, 1800.0] rpm (mín=1708, máx=1803)
ValueError: rpm: 1 de 4200 leituras fora da faixa [1650.0, 1800.0] rpm (mín=1712, máx=1803)
ValueError: pressao: 5 de 16800 leituras fora da faixa [3.0, 4.5] bar (mín=3.179, máx=4.565)
ValueError: pressao: 1 de 4200 leituras fora da faixa [3.0, 4.5] bar (mín=3.264, máx=4.511)

4 failed, 72 passed
```

**Contagem por conjunto** (o que o relatório cita):

| conjunto | linhas | rpm fora de faixa | pressão convertida fora de faixa |
|---|---:|---:|---:|
| treino | 16.800 | 4 | 5 |
| teste | 4.200 | **0** | **0** |
| producao | 4.200 | 1 | 1 |

**O achado que vale o relatório:** o conjunto de **teste é o único limpo**. Quem só olha a
métrica de teste — que é exatamente o que a equipe da Nortemec fez para decidir promover a
v2 — nunca vê a violação. O defeito está no treino e volta em produção.

Consequência para a suíte: o `xfail(strict=True)` é aplicado **por conjunto**, só em
`treino` e `producao`. Marcar os três derrubaria a suíte por XPASS em `teste`, que passa
legitimamente.

**Patch:** não (SPEC §4.3 classifica como parcial, via D03).

---

## D03 — `unidade_pressao` é normalizada mas nunca usada para converter

**Onde:** `tests/test_preprocessamento.py` · **Medido em:** 20260924, HANDOFF 02 Etapa 4
**Causa raiz:** `unidade_pressao` é normalizada mas nunca usada para converter
**Impacto na planta:** a mesma pressão física gera decisões diferentes conforme o CLP: a árvore virou detector de fabricante
**Teste que o mata:** `test_limpar_converte_pressao_de_psi_para_bar`


`test_limpar_converte_pressao_de_psi_para_bar`, com o lote inteiro em psi:

```
Not equal to tolerance rtol=1e-09
Mismatched elements: 144 / 144 (100%)
 [0]: 50.67153778458743 (ACTUAL), 3.4936732294010833 (DESIRED)
Max relative difference among violations: 13.5038
```

A razão entre medido e esperado é **14,5038** — o fator psi→bar inteiro. O SUT entrega o
número em psi rotulado como bar. A árvore aprendeu a separar fabricante de CLP, não pressão.

## D19 — só `.lower()`, sem checar o domínio da unidade

**Onde:** `tests/test_preprocessamento.py` · **Medido em:** 20260924, HANDOFF 02 Etapa 4
**Causa raiz:** só `.lower()` em `unidade_pressao`, sem checar o domínio
**Impacto na planta:** um CLP novo com uma terceira unidade entra sem aviso
**Teste que o mata:** `test_limpar_rejeita_unidade_de_pressao_desconhecida`


`test_limpar_rejeita_unidade_de_pressao_desconhecida`, com `unidade_pressao="kgf/cm2"`:

```
Failed: DID NOT RAISE ValueError
```

## D04 — `fillna(0.0)` com 0,0 fora da faixa física 1,2–8,0 mm/s

**Onde:** `tests/test_preprocessamento.py` · **Medido em:** 20260924, HANDOFF 02 Etapa 4
**Causa raiz:** `fillna(0.0)` imputa 0,0 mm/s, fora da faixa física 1,2–8,0 do sensor
**Impacto na planta:** falha do sensor de vibração é lida como motor parado e altera ordens de manutenção
**Teste que o mata:** `test_vibracao_imputada_fica_na_faixa_fisica_do_sensor`


```
AssertionError: 25 valores imputados fora da faixa física [1.2, 8.0] mm/s; exemplo: [0. 0. 0.]
```

## D05 — descarte silencioso de linhas, e o corte no lugar errado

**Onde:** `tests/test_preprocessamento.py` · **Medido em:** 20260924, HANDOFF 02 Etapa 4
**Causa raiz:** `limpo[limpo['rpm'] >= 1.0]` descarta sem registro, e 1,0 rpm não é eixo girando
**Impacto na planta:** motores somem do painel sem ninguém saber, e leitura inválida atravessa como boa
**Teste que o mata:** `test_limpar_nao_descarta_linhas_silenciosamente`, `test_limpar_descarta_so_o_que_a_ficha_chama_de_eixo_parado`, `test_pipeline_nao_perde_linhas_silenciosamente`


```
AssertionError: 1 linhas desapareceram sem auditoria
AssertionError: rpm=5 atravessou a limpeza: o SUT só corta abaixo de 1.0
```

Os dois lados do mesmo defeito: o SUT corta em `rpm >= 1.0` **sem registrar**, e o corte
em 1,0 não é o que a ficha chama de eixo girando (1.650 rpm). Leitura inválida entra;
leitura válida some.

## D16 — `limpar` não desduplica `(id_maquina, timestamp)`

**Onde:** `tests/test_preprocessamento.py` · **Medido em:** 20260924, HANDOFF 02 Etapa 4
**Causa raiz:** `limpar` não desduplica `(id_maquina, timestamp)`
**Impacto na planta:** reenvio do historiador dobra o peso de uma leitura nas janelas
**Teste que o mata:** `test_limpar_desduplica_a_chave_id_maquina_timestamp`


```
AssertionError: 1 chaves duplicadas sobreviveram à limpeza
```

## D18 — `.astype(int)` sem validação prévia

**Onde:** `tests/test_preprocessamento.py` · **Medido em:** 20260924, HANDOFF 02 Etapa 4
**Causa raiz:** `.astype(int)` sem validação prévia
**Impacto na planta:** plantão às 3 h da manhã com erro do pandas e sem saber qual coluna quebrou
**Teste que o mata:** `test_limpar_falha_com_mensagem_que_nomeia_a_coluna[coluna]`


`test_limpar_falha_com_mensagem_que_nomeia_a_coluna[turno|idade_equipamento_meses|id_operador]`:

```
AssertionError: Regex pattern did not match.
```

Levanta, mas a mensagem não nomeia a coluna — é o `Cannot convert non-finite values` cru
do pandas. Plantão às 3h da manhã sem saber onde olhar.

## D22 — `reset_index(drop=True)`

**Onde:** `tests/test_preprocessamento.py` · **Medido em:** 20260924, HANDOFF 02 Etapa 4
**Causa raiz:** `reset_index(drop=True)` descarta a rastreabilidade da linha de origem
**Impacto na planta:** com D05 ativo, não há auditoria de quais leituras foram ignoradas
**Teste que o mata:** `test_limpar_preserva_rastreabilidade_da_linha_original`


```
AssertionError: não há como casar a linha de saída com a de entrada: o índice foi
reconstruído como RangeIndex 0..142 e nenhuma coluna de origem foi preservada
```

Só aparece quando alguma linha é descartada; com o lote inteiro sobrevivendo, o índice
reconstruído coincide com o original por acidente. O primeiro teste que escrevi passava
por esse motivo — registrado aqui porque é um jeito fácil de escrever um teste inútil.

---

## D07 — `prever_registro` ignora as chaves do dicionário

**Onde:** `tests/test_modelo_contrato.py` · **Medido em:** 20260924, HANDOFF 02 Etapa 4

`prever_registro` faz `[float(valor) for valor in registro.values()]`: monta o vetor pela
**ordem de inserção** do dicionário e nunca olha as chaves. É o caminho do painel da sala
de controle, que recebe um registro por vez.

```
AssertionError: 39 de 72 leituras (54.2%) mudam de decisão só por reordenar
as chaves do dicionário; primeiras: [4, 5, 6, 7, 8]

Failed: DID NOT RAISE ValueError        # chave inventada entra como se fosse feature
```

**Cuidado ao reproduzir:** numa linha só, as duas decisões coincidem em ~46 % dos casos.
A primeira versão deste teste olhava `features.iloc[0]` e **passava** — o defeito só
aparece varrendo o lote. Um teste de defeito que passa é pior que teste nenhum: dá a
impressão de que a costura foi verificada.

**Patch:** opcional (SPEC §4.3).

---

## D01 ★ — vazamento temporal: `rolling(6, center=True)`

**Onde:** `tests/test_features.py` · **Medido em:** 20260924, HANDOFF 02 Etapa 5
É o defeito central da entrega.

### O experimento

Lote de 3 motores × 48 h. Perturbamos **somente** as leituras posteriores a `t=20` do
motor M01, somando +10,0 °C. Nenhuma leitura até `t` é tocada. Se a feature de `t` usasse
só o passado, nada em `t` poderia se mexer.

### Os dois controles positivos — passam

| Teste | Janela | Resultado |
|---|---|---|
| `test_temp_max_24h_nao_muda_quando_so_o_futuro_muda` | `rolling(24, min_periods=1)` | **passa** |
| `test_vib_media_6h_nao_muda_quando_so_o_futuro_muda` | `rolling(6, min_periods=1)` | **passa** |

São eles que dão autoridade ao terceiro: o experimento é o mesmo, o lote é o mesmo, a
perturbação é a mesma. A única diferença é o `center=True`.

### O teste-estrela — falha

```
AssertionError: temp_media_6h[t=20] mudou 3.3333 °C ao perturbar APENAS t+1..t+123
em +10.0 °C; 29 linhas do lote mudaram no total
```

`rolling(6, center=True)` faz a janela ser `[t−2, t+3]`. Na hora `t`, a planta **não tem**
`t+1`, `t+2`, `t+3` — o historiador ainda não os registrou. O desempenho medido no
conjunto de teste é, por construção, inalcançável em produção.

**Patch:** **sim**. Remove uma palavra (`center=True`) e **não** toca `min_periods`, para
não introduzir NaN nas primeiras linhas de cada motor — o que faria `_matriz` levantar
`ValueError` e derrubaria até o teste de exemplo do próprio SUT (SPEC D10).

---

## D08 — `rolling(24)` / `shift(24)` contam linhas, não horas

**Onde:** `tests/test_features.py` · **Medido em:** 20260924, HANDOFF 02 Etapa 5
**Causa raiz:** as janelas e o `shift` contam **posições**, e o historiador tem furos.
**Impacto na planta:** depois de qualquer buraco de coleta, "variação em 24 h" é outra grandeza.
**Teste que o mata:** `test_delta_temp_24h_compara_com_a_leitura_de_vinte_e_quatro_horas_antes`

```
delta_temp_24h em 2026-01-02 21:00:00 devolveu 0.2128 °C, mas a diferença real contra
2026-01-01 21:00:00 é -8.3229 °C: com 5 h de furo, `shift(24)` foi buscar a leitura de 29 h antes
```

## D09 — a feature de um motor depende de quem mais estava no lote

**Onde:** `tests/test_features.py` · **Medido em:** 20260924, HANDOFF 02 Etapa 5
**Causa raiz:** `center=True`, `min_periods=1` e `maquina_risco` calculada por lote.
**Impacto na planta:** reprocessar a mesma janela dá outra resposta para as mesmas leituras.
**Teste que o mata:** `test_construir_e_estavel_entre_o_lote_inteiro_e_um_recorte`

```
reprocessar as últimas 24 h muda 7 das 13 features das mesmas linhas:
{'temp_media_6h': 2.3586, 'temp_max_24h': 17.8702, 'delta_temp_24h': 28.9387,
 'vib_media_6h': 1.2126, 'vib_max_24h': 3.9664, 'corrente_media_6h': 4.405,
 'maquina_risco': 0.0417}
```

**Cuidado ao reproduzir:** recortar **por motor** não expõe nada — as janelas já são por motor e
`maquina_risco` é calculada dentro do próprio motor. O recorte tem de ser **temporal**, que é como
a planta reprocessa de verdade. A primeira versão deste teste recortava por motor e passava.

## D10 — `saida.loc[df.index, …]` com rótulos repetidos multiplica as linhas

**Onde:** `tests/test_features.py` · **Medido em:** 20260924, HANDOFF 02 Etapa 5
**Causa raiz:** indexação por rótulo num quadro com índice duplicado.
**Impacto na planta:** `pd.concat` de dois lotes, fluxo natural de reprocessamento, explode o quadro.
**Teste que o mata:** `test_construir_aceita_indice_duplicado_sem_multiplicar_linhas`

```
`saida.loc[df.index]` com rótulos repetidos explodiu o quadro: 48 linhas de entrada viraram 96
```

## D15 — a validação de colunas cobre 4 das 11 que `construir` consome

**Onde:** `tests/test_features.py` · **Medido em:** 20260924, HANDOFF 02 Etapa 5
**Causa raiz:** a checagem explícita lista só 4 colunas; o resto quebra com `KeyError` cru.
**Impacto na planta:** o caso de uso de uma leitura só — o painel — é o mais frágil e o menos protegido.
**Teste que o mata:** `test_construir_nomeia_a_coluna_faltante_tambem_para_pressao_e_rpm[coluna]`

```
ValueError não levantado para `pressao` nem para `rpm`: a checagem de colunas de `construir`
cobre 4 das 11 colunas que ele consome; o resto vira KeyError cru
```

## D20 — `min_periods=1` transforma buraco de sensor em número confiante

**Onde:** `tests/test_features.py` · **Medido em:** 20260924, HANDOFF 02 Etapa 5
**Causa raiz:** a janela ignora o NaN e o `delta` cai no `fillna(0.0)`.
**Impacto na planta:** temperatura ausente produz predição confiante, sem sinal de que faltou dado.
**Teste que o mata:** `test_temperatura_ausente_nao_e_silenciosamente_imputada`

```
temperatura ausente virou média finita [69.628, 71.502, 75.736, 70.488]: o buraco do sensor
foi imputado sem que ninguém pedisse
```

---

## D11 ★ — acurácia premia quem não prevê falha, e o limiar 0,5 não é o da planta

**Onde:** `tests/test_estatistico_limiar_calibracao.py`, `tests/test_estatistico_v1_v2.py`
**Medido em:** 20260924, HANDOFF 04 Etapas 2 e 3 · conjunto **teste**, modo **sem vazamento**

Prevalência de ~15 %: o preditor sempre-zero já acerta 84 %. A v2 é uma floresta mais profunda
sem reponderação, e compra acurácia entregando recall — que é a única coisa que a manutenção
compra.

### Vermelho, antes de qualquer marker

```
v1: F2 é máximo em 0.55 (F2=0.7356), não em 0,50 (F2=0.7346); diferença de +0.0010
v2: F2 é máximo em 0.20 (F2=0.7375), não em 0,50 (F2=0.6510); diferença de +0.0865
v2: custo mínimo em 0.15 (custo=1788), não em 0,50 (custo=4393);
    o limiar do sistema custa 2605 a mais
```

### O achado que não estava previsto: para a v1, o 0,5 **é** o limiar de custo mínimo

`test_limiar_de_custo_minimo_e_0_5[v1]` **passou**. Com FN valendo 20× FP, o custo da v1 é
mínimo exatamente em 0,50 (1.765). O HANDOFF 04 antecipava que o limiar de custo mínimo não
seria 0,5 — e para a v1 ele é.

| versão | custo em 0,50 | limiar de custo mínimo | custo lá |
|---|---:|---:|---:|
| v1 | **1.765** | 0,50 | 1.765 |
| v2 | 4.393 | 0,15 | 1.788 |

Isso muda o argumento, e para melhor:

1. **O 0,5 não é um default distraído no sistema em produção** — ele é, por sorte ou por
   escolha, ótimo para a v1 sob o custo da planta.
2. **Promover a v2 sem retocar o limiar multiplica o custo por 2,5** (1.765 → 4.393). O
   defeito não é o limiar em si: é promover um modelo e herdar o limiar do anterior.
3. **Mesmo no seu melhor limiar, a v2 não vence.** 1.788 contra 1.765 — a v2 reajustada
   apenas empata com a v1 como está hoje. Não há ganho a recuperar por calibração de limiar.

**Consequência de marcação:** `xfail(strict=True)` na função inteira viraria XPASS em `[v1]` e
derrubaria a suíte. A marca vai no `pytest.param` da v2, como em D17 (`docs/decisoes.md`, "xfail
por parâmetro quando o defeito não está em todo lugar"). O `[v1]` fica **verde e vale como
resultado**, não como ausência de defeito.

**Ressalva de honestidade para o relatório:** em `test_limiar_0_5_maximiza_f2[v1]` a diferença é
de +0,0010 de F2 entre 0,55 e 0,50 — tecnicamente o 0,5 não é o argmax, materialmente é
irrelevante. Quem citar esse número sem a magnitude estará exagerando. O caso forte é a v2
(+0,0865), e é esse que vai para a conclusão.

### Vermelho da Etapa 3 — a comparação v1 × v2 (teste, sem vazamento)

```
recall v1=0.9374, v2=0.6977: a v2 perde 23.97 pp de recall — deixa de pegar 157 falhas
    reais a mais que a v1
producao/sem vazamento: PR-AUC v1=0.6433, v2=0.6379 (-0.54 pp)
```

### A incerteza, que é o que o enunciado cobra

| medida | valor | leitura |
|---|---|---|
| IC pareado do Δrecall, `recall(v1) − recall(v2)` | **[0,2075; 0,2698]** | `lo > 0` ⇒ **v1 melhor**, com significância |
| McNemar exato sobre as falhas reais | `n01=0`, `n10=157`, `p = 1,1e-47` | **v1 melhor** |
| discordantes | 669 no lote inteiro; 157 entre as falhas | |

**`n01 = 0` é o número mais forte do trabalho.** Não existe **uma única** falha real que a v2
pegue e a v1 perca. A v1 pega 614 das 655 falhas do conjunto; a v2 pega 457 — e essas 457 são
**subconjunto** das 614. A v2 não troca um tipo de acerto por outro: ela só perde. O `157` do
`n10` é exatamente o número de falhas a mais que a v1 pega, e casa com os 23,97 pp de Δrecall.

### PR-AUC: o único lugar em que a v2 ganha, e onde ela ganha importa

| conjunto (sem vazamento) | PR-AUC v1 | PR-AUC v2 | v2 é pior? |
|---|---:|---:|---|
| teste | 0,5811 | 0,6718 | não (**+9,07 pp** para a v2) |
| producao | 0,6433 | 0,6379 | **sim** (−0,54 pp) |

`test_pr_auc_da_v2_nao_e_pior_que_a_da_v1[teste]` **passa**: como ranqueadora, no conjunto de
teste, a v2 é melhor. Em produção a vantagem some. Marcar a função inteira daria XPASS em
`[teste]` — o `xfail` vai no `pytest.param` de `producao` (padrão de D17).

Isto merece o relatório com a ressalva junto: **a v2 não é um modelo ruim, é um modelo ruim
para esta decisão.** Ela ranqueia melhor no teste e calibra melhor em toda parte (ver D12); o
que ela não faz é pegar falha no limiar em que o sistema opera. Dizer "a v2 é pior" sem
qualificar seria o mesmo erro de leitura, com o sinal trocado, que a Nortemec cometeu.

---

## D12 — floresta profunda sem reponderação produz probabilidade que não é probabilidade

**Onde:** `tests/test_estatistico_limiar_calibracao.py` · **Medido em:** 20260924, HANDOFF 04
Etapa 2 · conjunto **teste**, modo **sem vazamento**

### Vermelho, antes de qualquer marker

```
v1: ECE = 0.1906 (19.06 p.p.)
v2: ECE = 0.0576 (5.76 p.p.)

v1: 3 quebra(s) de monotonia: faixa 0.1–0.2 caiu de 0.0169 para 0.0096;
    faixa 0.2–0.3 caiu de 0.0096 para 0.0000; faixa 0.4–0.5 caiu de 0.0250 para 0.0247
v2: 1 quebra(s) de monotonia: faixa 0.5–0.6 caiu de 0.3033 para 0.2864

v1: maior desvio |confiança − observado| = 0.4227; piores faixas:
    0.4–0.5 prometeu 0.4473 e observou 0.0247 (n=162);
    0.7–0.8 prometeu 0.7573 e observou 0.3464 (n=332);
    0.6–0.7 prometeu 0.6504 e observou 0.2589 (n=394)
v2: maior desvio |confiança − observado| = 0.3140; piores faixas:
    0.6–0.7 prometeu 0.6486 e observou 0.3345 (n=278);
    0.5–0.6 prometeu 0.5454 e observou 0.2864 (n=220);
    0.4–0.5 prometeu 0.4592 e observou 0.3033 (n=211)
```

### A curva de confiabilidade, por faixa

| faixa | n (v1) | conf. v1 | obs. v1 | n (v2) | conf. v2 | obs. v2 |
|---|---:|---:|---:|---:|---:|---:|
| 0,0–0,1 | 1780 | 0,0321 | 0,0169 | 2449 | 0,0154 | 0,0139 |
| 0,1–0,2 | 314 | 0,1434 | 0,0096 | 283 | 0,1450 | 0,0636 |
| 0,2–0,3 | 225 | 0,2472 | 0,0000 | 190 | 0,2467 | 0,1895 |
| 0,3–0,4 | 160 | 0,3582 | 0,0250 | 177 | 0,3451 | 0,2599 |
| 0,4–0,5 | 162 | 0,4473 | 0,0247 | 211 | 0,4592 | 0,3033 |
| 0,5–0,6 | 219 | 0,5577 | 0,2055 | 220 | 0,5454 | 0,2864 |
| 0,6–0,7 | 394 | 0,6504 | 0,2589 | 278 | 0,6486 | 0,3345 |
| 0,7–0,8 | 332 | 0,7573 | 0,3464 | 222 | 0,7486 | 0,7027 |
| 0,8–0,9 | 367 | 0,8405 | 0,5232 | 137 | 0,8414 | 0,8321 |
| 0,9–1,0 | 247 | 0,9305 | 0,6478 | 33 | 0,9513 | 0,9394 |

**O gap é positivo nas 20 faixas das duas versões: os dois modelos são superconfiantes em toda
a escala.** Nunca prometem de menos.

### A leitura que inverte a conclusão do Bloco B — e que é o ponto do relatório

**A v2 é o modelo mais bem calibrado.** Brier 0,0917 contra 0,1523; ECE 5,76 p.p. contra
19,06 p.p.; uma quebra de monotonia contra três. Se a escolha fosse por qualidade de
probabilidade, a v2 ganharia com folga.

E ainda assim a v2 é a que deixa passar motor: recall 0,6977 contra 0,9374 no mesmo conjunto e
modo. **"Melhor calibrado" e "melhor para a planta" não são a mesma coisa**, e a v1 — que mente
mais no número — é a que abre as ordens de manutenção certas. É o argumento mais forte contra
escolher versão por um número só, qualquer que seja o número.

**Ressalva:** o ECE da v2 (5,76 p.p.) fica **logo acima** do corte de 5 p.p. do teste. O
veredito "a v2 também é malcalibrada" repousa numa margem de 0,76 p.p. e não deve ser
apresentado com a mesma força do da v1. O que se sustenta sem ressalva é a superconfiança: 20
de 20 faixas com gap positivo.

---

## D13 — produção já não é o teste, e nada no sistema observa isso

**Onde:** `tests/test_estatistico_drift.py` · **Medido em:** 20260924, HANDOFF 04 Etapa 4
Baseline = conjunto `teste`; comparado = `producao`.

### Vermelho, antes de qualquer marker

```
5 de 6 colunas acusam drift:
  temperatura_c  (KS p=3.53e-33, PSI=0.1798 → atencao, mas Δmédia de só 1.76 %)
  vibracao_rms   (KS p=1.14e-21, PSI=0.1403 → atencao, mas Δmédia de só 2.05 %)
  pressao        (KS p=1.6e-05,  PSI=0.0520 → estavel, mas Δmédia de só 0.65 %)
  corrente_a     (KS p=3.19e-11, PSI=0.0575 → estavel, mas Δmédia de só 0.52 %)
  rpm            (KS p=9.76e-07, PSI=0.0203 → estavel, mas Δmédia de só 0.05 %)
```

### Os três detectores, lado a lado

| coluna | Δmédia relativa | média acusa? | KS p | KS D | PSI | classe |
|---|---:|---|---|---:|---:|---|
| temperatura_c | 1,76 % | não | 3,53e-33 | 0,1338 | 0,1798 | atenção |
| vibracao_rms | 2,05 % | não | 1,14e-21 | 0,1129 | 0,1403 | atenção |
| pressao | 0,65 % | não | 1,6e-05 | 0,0529 | 0,0520 | estável |
| corrente_a | 0,52 % | não | 3,19e-11 | 0,0769 | 0,0575 | estável |
| rpm | 0,05 % | não | 9,76e-07 | 0,0588 | 0,0203 | estável |
| idade_equipamento_meses | 0,00 % | não | 1,0 | 0,0000 | 0,0000 | estável |

**A diferença de médias fica calada em 6 de 6 colunas.** Nenhuma chega perto do limiar de
10 %: a maior é 2,05 %. Um monitoramento construído sobre médias — que é o que se constrói
primeiro, porque é o mais barato — reportaria "tudo estável" enquanto cinco das seis entradas
mudaram de distribuição.

**E o KS sozinho enganaria na direção oposta.** `p = 3,5e-33` em `temperatura_c` parece
catástrofe; o `D` correspondente é 0,1338 e o PSI, 0,18 — faixa de **atenção**, não de drift
severo. Com n = 4.200 por lado, p minúsculo é o que se espera de qualquer diferença real, por
pequena que seja. `pressao` é o caso limpo: KS acusa (p = 1,6e-05) e o PSI diz 0,052, estável.

**É por isso que os três entram no relatório juntos.** Escolher um detector é escolher o que
se aceita não enxergar: a média aceita não ver mudança de forma; o KS aceita não distinguir
efeito grande de pequeno; o PSI aceita a arbitrariedade das faixas. Os números à vista, e a
escolha explícita, é o que a suíte entrega no lugar de um alarme.

### O que **não** é drift, e por isso não entra aqui

Medido no mesmo passo e registrado em `medicoes.json` → `estabilidade`:

| grandeza | treino | teste | producao | teste × producao |
|---|---:|---:|---:|---:|
| dropout de vibração | 0,0724 | 0,0971 | 0,0840 | 1,31 p.p. |
| proporção em psi | 0,3200 | 0,3200 | 0,3200 | **0,00 p.p.** |
| prevalência do alvo | 0,1154 | 0,1560 | 0,1426 | 1,34 p.p. |

Os três passam com folga na tolerância de 2 p.p. entre baseline e produção. **O drift está na
forma das distribuições de sensor, não na qualidade do dado nem na mistura de CLPs** — o que
torna o achado mais limpo, porque exclui as explicações alternativas baratas.

---

## D14 ★ — a decisão muda dentro do erro do próprio sensor

**Onde:** `tests/test_adversarial.py` · **Medido em:** 20260925, HANDOFF 05 Etapa 2
**Causa raiz:** fronteiras de decisão de floresta profunda passam dentro do erro do sensor
**Impacto na planta:** duas leituras fisicamente indistinguíveis do mesmo motor geram ordens opostas
**Teste que o mata:** `test_perturbacao_menor_que_o_ruido_do_sensor_nao_muda_a_decisao[amplitude]`
e `test_v2_nao_e_mais_instavel_que_a_v1[amplitude]`

A ficha técnica do SUT declara ruído de **±1,0 °C** na temperatura. O número é um contrato:
ele diz que o sensor **não consegue** separar duas leituras que difiram por menos que isso.
Perturbar abaixo dele é reler o mesmo motor — não é criar um motor diferente.

### O vermelho, antes de qualquer marker

```
6 failed, 3 passed in 3.11s

test_perturbacao_menor_que_o_ruido_do_sensor_nao_muda_a_decisao[0.1]
E   AssertionError: perturbação de ±0.1 °C — 10% do ruído declarado de ±1.0 °C — mudou
    decisões: v1: 0.2857% (12 decisões — 12 para cima, 0 para baixo);
              v2: 0.4286% (18 decisões — 10 para cima, 8 para baixo)

test_perturbacao_menor_que_o_ruido_do_sensor_nao_muda_a_decisao[0.2]
E   AssertionError: perturbação de ±0.2 °C — 20% do ruído declarado de ±1.0 °C — mudou
    decisões: v1: 0.5714% (24 decisões — 17 para cima, 7 para baixo);
              v2: 1.0476% (44 decisões — 25 para cima, 19 para baixo)

test_perturbacao_menor_que_o_ruido_do_sensor_nao_muda_a_decisao[0.4]
E   AssertionError: perturbação de ±0.4 °C — 40% do ruído declarado de ±1.0 °C — mudou
    decisões: v1: 1.0238% (43 decisões — 28 para cima, 15 para baixo);
              v2: 1.2381% (52 decisões — 29 para cima, 23 para baixo)

test_v2_nao_e_mais_instavel_que_a_v1[0.1]
E   AssertionError: a ±0.1 °C a v2 vira 0.4286% das decisões contra 0.2857% da v1 —
    1.50× mais instável (v2: 10↑/8↓; v1: 12↑/0↓)

test_v2_nao_e_mais_instavel_que_a_v1[0.2]
E   AssertionError: a ±0.2 °C a v2 vira 1.0476% das decisões contra 0.5714% da v1 —
    1.83× mais instável (v2: 25↑/19↓; v1: 17↑/7↓)

test_v2_nao_e_mais_instavel_que_a_v1[0.4]
E   AssertionError: a ±0.4 °C a v2 vira 1.2381% das decisões contra 1.0238% da v1 —
    1.21× mais instável (v2: 29↑/23↓; v1: 28↑/15↓)
```

### A tabela medida (`medicoes.json → flip`, conjunto teste, sem vazamento, semente 42)

| amplitude | % do ruído | v1 — taxa | v1 ↑ | v1 ↓ | v2 — taxa | v2 ↑ | v2 ↓ |
|---:|---:|---:|---:|---:|---:|---:|---:|
| ±0,1 °C | 10 % | 0,2857 % | 12 | **0** | 0,4286 % | 10 | **8** |
| ±0,2 °C | 20 % | 0,5714 % | 17 | 7 | 1,0476 % | 25 | 19 |
| ±0,4 °C | 40 % | 1,0238 % | 28 | 15 | 1,2381 % | 29 | 23 |
| ±1,0 °C | **100 %** | 1,9524 % | 53 | 29 | 2,5000 % | 62 | 43 |

**O caso mais forte é o primeiro.** A um décimo do ruído declarado — uma diferença que
nenhum instrumento da planta consegue registrar — **12 motores** mudam de ordem na v1 e
**18** na v2. Não é um fenômeno de cauda que aparece só no extremo: ele está presente já
na menor amplitude testada e cresce monotonicamente.

### A direção importa mais que a taxa

`para_baixo` é o alarme que some, e portanto o motor que queima. A ±1,0 °C são **29**
alarmes perdidos na v1 e **43** na v2, só por ruído de medição. Reportar apenas a taxa
agregada (1,95 % e 2,50 %) esconde exatamente o erro caro — é a mesma assimetria de 20×
que o limiar de custo do Bloco B assume.

**Um detalhe da v1 a ±0,1 °C:** `12↑/0↓`. Na menor amplitude a v1 só erra para o lado
barato; a v2 já perde 8 alarmes. A robustez das duas não difere só em grau.

### A v2 é mais instável em **4 de 4** amplitudes

Entre 1,21× e 1,83×, sem exceção. Isto é um **terceiro eixo** independente contra a
promoção da v2, e não uma releitura dos anteriores: o Bloco B mostrou que ela perde recall
no limiar herdado (D11) e que nenhum limiar dela domina a v1 (`docs/decisoes.md`); aqui ela
perde também em estabilidade sob o erro do sensor. A floresta mais profunda tem mais
fronteiras de decisão, e mais fronteiras significam mais chance de que uma delas caia dentro
do erro de medição.

### O par legítimo passa — e é o que dá sentido ao resto

`test_mudanca_fisica_real_de_temperatura_muda_a_decisao` é **verde**: +15 °C sustentados
por 24 h nas 600 linhas do recorte levantam **126** alarmes na v1 e **150** na v2, contra
**8** e **1** do ruído de ±0,4 °C aplicado às **mesmas** 600 linhas. O modelo responde à
física — o problema não é insensibilidade, é sensibilidade no lugar errado.

Sem esse par o arquivo inteiro seria vazio: um modelo que ignorasse a temperatura passaria
em todos os testes de invariância acima com nota máxima. É a lição da aula 4 — a invariância
perfeita e a inutilidade perfeita são indistinguíveis por um oráculo de igualdade.

**Patch:** **não**. Corrigir exigiria retreinar com suavização de fronteira ou reponderação,
e o nosso repositório não altera o pacote sob teste (SPEC C12). D14 fica documentado e
medido; a recomendação vai no `relatorio.md`.

---

## D06 ★ — `operador_senior` é escalação reativa, não física do motor

**Onde:** `tests/test_adversarial.py` · **Medido em:** 20260925, HANDOFF 05 Etapa 3
**Causa raiz:** `operador_senior` codifica quem a manutenção escalou, não o estado do equipamento
**Impacto na planta:** o modelo aprendeu "o sênior foi chamado", que só é verdade **depois** de alguém já suspeitar da falha
**Teste que o mata:** `test_trocar_o_operador_senior_nao_muda_a_decisao`

O próprio comentário do SUT entrega a causa, em `features.construir`:

```python
# O técnico sênior (OP-07) é escalado para os motores mais críticos da
# planta; a equipe de manutenção pediu essa marcação explícita.
saida["operador_senior"] = (ordenado["id_operador"] == OPERADOR_SENIOR).astype(float)
```

### O vermelho, antes de qualquer marker

```
AssertionError: trocar OP-07 por OP-03 em 1008 leituras, sem tocar em nenhum sensor,
mudou: v1: 57 decisões (0↑/57↓) — 5.65% das linhas de OP-07;
       v2: 155 decisões (0↑/155↓) — 15.38% das linhas de OP-07.
Taxa de falha observada: OP-07 0.3988 contra 0.0794 na média dos outros onze
```

### Todos os flips são para baixo — **0↑ / 57↓** e **0↑ / 155↓**

Não é um efeito difuso de ruído: é **direcional**. Apagar o nome do técnico sênior da ficha
**só faz alarme sumir**, nunca aparecer. Em 1.008 leituras com sensores bit-idênticos, a v1
perde 57 ordens de manutenção e a v2 perde 155.

### O confundidor, medido

| operador | leituras | taxa de falha |
|---|---:|---:|
| **OP-07** | 1.008 | **0,3988** |
| OP-02 | 306 | 0,0948 |
| OP-05 | 286 | 0,0979 |
| OP-08 | 267 | 0,0899 |
| OP-12 | 288 | 0,0833 |
| OP-06 | 293 | 0,0785 |
| OP-03 | 269 | 0,0743 |
| OP-10 | 297 | 0,0741 |
| OP-11 | 286 | 0,0734 |
| OP-04 | 295 | 0,0712 |
| OP-01 | 297 | 0,0707 |
| OP-09 | 308 | 0,0649 |

**OP-07 tem 5× a taxa de falha da média dos outros onze** (0,3988 contra 0,0794) e responde
por 24 % das leituras do lote, o dobro de qualquer colega. A correlação é real e o modelo a
capturou; o que não existe é a **causa**. O sênior não faz o motor falhar — ele é chamado
porque alguém já percebeu que vai falhar.

**A consequência operacional é a pior possível:** a feature funciona bem exatamente quando
não é necessária, e desaparece exatamente quando seria útil. Um motor que começa a degradar
sem que ninguém tenha notado ainda não tem o sênior escalado — e é o único caso em que a
manutenção preditiva teria valor.

### É a feature **mais influente** das treze

`test_sensibilidade_por_feature_aponta_dependencia_ilegitima` (verde) mede, invertendo uma
feature por vez: `operador_senior` fica em **1º de 13 nas duas versões**, com `delta_medio`
de **0,104084** (v1) e **0,094466** (v2) — 1,7× a 2,1× a segunda colocada, e mais que
`pressao`, `rpm` e `delta_temp_24h` somadas.

**Patch:** não (exigiria retreino sem a feature). Vai como recomendação no `relatorio.md`.

---

## D03 (adversarial) — a mesma pressão física, dois rótulos de unidade, duas decisões

**Onde:** `tests/test_adversarial.py` · **Medido em:** 20260925, HANDOFF 05 Etapa 3
**Teste que o mata:** `test_converter_a_pressao_para_a_outra_unidade_nao_muda_a_decisao`

Segundo ângulo sobre D03 (o primeiro está acima, no Bloco A): aqui o defeito aparece como
**teste metamórfico de unidade**, no espírito do Mars Climate Orbiter da aula 3. A
transformação preserva a grandeza física — multiplicar por `FATOR_PSI_POR_BAR = 14.5038` e
declarar a unidade — e a saída teria de ser invariante a ela.

### O vermelho, antes de qualquer marker

```
AssertionError: converter 2856 leituras de bar para psi — multiplicando por 14.5038 e
declarando a unidade — mudou: v1: 24 decisões (5↑/19↓); v2: 83 decisões (71↑/12↓).
A pressão física é a mesma; só o rótulo da unidade mudou
```

### Por que isso acontece: a coluna já mistura duas escalas

| unidade | linhas | mín | máx | média |
|---|---:|---:|---:|---:|
| bar | 2.856 | 3,205 | 4,433 | 3,901 |
| psi | 1.344 | 48,362 | 64,679 | 56,510 |

`limpar` normaliza `unidade_pressao` para minúsculas e **nunca a usa**; `construir` consome
`pressao` crua. A floresta não tem como ler isso senão como um corte em torno de 10: de um
lado os CLPs que reportam em bar, do outro os que reportam em psi. **A árvore não mede
pressão — ela detecta o fabricante do CLP.**

Trocar o CLP de um motor, operação rotineira de manutenção que não altera nada físico,
muda a decisão sobre aquele motor.

**Patch:** **sim** — é o patch D03, que converte a pressão usando `unidade_pressao` (e
carrega junto a rejeição de unidade desconhecida, D19).

---

## D04 (adversarial) — a constante que tapa o buraco do sensor decide a ordem de manutenção

**Onde:** `tests/test_adversarial.py` · **Medido em:** 20260925, HANDOFF 05 Etapa 3
**Teste que o mata:** `test_dropout_de_vibracao_nao_muda_as_decisoes_da_janela`

`limpar` preenche a vibração ausente com `0,0`, valor **fora** da faixa física de 1,2 a
8,0 mm/s da ficha técnica. Para o modelo, "o sensor falhou" fica indistinguível de "o eixo
parou" — e o número viaja por até 24 h de janela móvel a partir do buraco.

### O oráculo teve de ser refeito (sexto caso da família)

O primeiro desenho seguia a letra do SPEC: apagar **uma** leitura e conferir as 24 h
afetadas. Ele **passou**. Medido, o motivo:

```
M01, 1 leitura apagada (2,009 -> 0,0):
  vib_media_6h muda em 11 linhas, |Δ| máx = 2,0910
  vib_max_24h  muda em 15 linhas, |Δ| máx = 0,1060
  v1: 9 linhas mudam de probabilidade, |Δp| máx = 0,023869
      decisões que viram: 0
```

O efeito existe e é grande na **feature**; o limiar de 0,5 o engole na **decisão**. É
exatamente a armadilha já catalogada em D02 ("asserte a probabilidade, não a decisão") e em
D07/D09/D22.

**O desenho que funciona não pergunta se perder uma leitura muda algo** — perder informação
pode legitimamente mudar. Ele pergunta **se a constante de imputação decide**: as mesmas
leituras ausentes, preenchidas com o mínimo físico da ficha (1,2 mm/s) em vez de 0,0. E usa
o dropout que o historiador **já produziu**, em vez de inventar um:

### O vermelho, antes de qualquer marker

```
AssertionError: trocar a constante de imputação de 0,0 para 1.2 mm/s — o mínimo físico da
ficha — nas 408 leituras ausentes (9.71% do lote) mudou: v1: 10 decisões (8↑/2↓);
v2: 29 decisões (22↑/7↓). Nenhuma medição nova entrou; só o número que tapa o buraco
```

### A extensão do estrago

| grandeza | medido |
|---|---:|
| leituras de vibração ausentes no lote de teste | **408** de 4.200 (9,71 %) |
| linhas na janela de influência de ao menos um `0,0` | **3.003** de 4.200 (**71,50 %**) |
| linhas que mudam de probabilidade ao reimputar com 1,2 | 1.444 (v1) · 1.483 (v2) |
| linhas que mudam de probabilidade ao reimputar com a mediana (3,1535) | 1.989 (v1) · 1.982 (v2) |
| decisões que viram com 1,2 (o valor válido mais próximo de 0,0) | 10 (v1) · 29 (v2) |
| decisões que viram com a mediana | 18 (v1) · 54 (v2) |

**1,2 mm/s é o piso do efeito, não o teto:** é o valor físico mais próximo de 0,0, escolhido
de propósito para ser o mais favorável ao SUT. Com a mediana das leituras válidas o número
quase dobra. E **71,5 % do lote** está na janela de influência de algum buraco — não é um
caso de borda, é o regime normal de operação deste historiador.

**Patch:** não. A correção é imputar dentro da faixa física (ou propagar o NaN e recusar a
predição), e vai como recomendação no `relatorio.md`.

---

## D15 (casos-limite) — o painel de um motor só é o caminho mais frágil do sistema

**Onde:** `tests/test_adversarial_limites.py` · **Medido em:** 20260925, HANDOFF 05 Etapa 4
**Causa raiz:** nenhuma validação de forma nem de tamanho de lote
**Impacto na planta:** o painel da sala de controle — o caso de uso de `prever_registro` — é o mais frágil
**Testes que o matam:** `test_lote_com_uma_linha_nao_produz_maquina_risco_degenerado`,
`test_lote_vazio_levanta_erro_claro`, `test_painel_de_um_registro_concorda_com_o_lote`

### O vermelho, antes de qualquer marker

```
test_lote_com_uma_linha_nao_produz_maquina_risco_degenerado
E   AssertionError: um lote de uma linha rotulada faz `maquina_risco` virar o próprio
    rótulo — rótulo 0: maquina_risco = 0.0 (tabela congelada de M01: 0.108631);
    rótulo 1: maquina_risco = 1.0 (tabela congelada de M01: 0.108631).
    A faixa que o modelo viu no treino é [0.0; 0.214286]

test_lote_vazio_levanta_erro_claro
E   Failed: o pipeline aceitou um lote vazio e devolveu um quadro de (0, 5) sem levantar
    nada: 'sem dado' fica indistinguível de 'sem risco'

test_painel_de_um_registro_concorda_com_o_lote
E   AssertionError: a mesma leitura recebe ordens diferentes conforme entre pelo lote ou
    pelo painel: linha 30: lote diz 1, painel diz 0 (maquina_risco 0.145833 no lote contra
    0.000000 no painel); linha 60: lote diz 1, painel diz 0 (0.187500 contra 0.000000);
    linha 90: lote diz 1, painel diz 0 (0.187500 contra 0.000000)
```

### `maquina_risco = 1,0` é 4,67× o maior valor que o modelo já viu

Com uma linha só, `groupby("id_maquina")["falha_72h"].transform("mean")` devolve o valor
daquela linha. É D02 na forma mais extrema — o alvo entra **inteiro** na feature — e o
número sai da faixa `[0; 0,214286]` da tabela congelada. Nenhuma árvore da floresta tem
corte acima de 0,214286: o modelo extrapola num regime que nunca foi treinado, e o resultado
é indefinido, não "conservador".

### As três ordens que somem

**3 de 3** leituras testadas que o lote noturno marcaria para manutenção recebem `0` no
painel. A causa é visível ao lado de cada uma: `maquina_risco` cai de 0,145833 e 0,187500
para **0,000000**, porque a linha sozinha não tem rótulo de falha e a média do grupo de um
elemento é zero.

O painel é o caminho pelo qual um operador consulta **um motor específico, agora** — o
momento em que a resposta mais importa. E é o caminho que sistematicamente responde "sem
risco".

### O lote vazio

O pipeline devolve `(0, 5)` e sai limpo. No painel, "o historiador não respondeu" fica
indistinguível de "nenhum motor em risco" — e as duas situações pedem ações opostas do
operador.

### A fronteira está entre uma linha e um motor, não em "lote pequeno"

`test_lote_com_um_motor_so_funciona` **passa**: 48 h de um motor atravessam o pipeline e
produzem decisão. O defeito não é fragilidade a lote pequeno; é a ausência de validação de
tamanho no ponto exato em que `groupby` degenera.

**Patch:** não. A correção é validar o tamanho do lote e usar a tabela congelada quando o
lote não sustenta uma média — e ela pertence ao patch de D02, não a este.

---

## D21 — o serving aceita 500 °C e devolve uma probabilidade com seis casas

**Onde:** `tests/test_adversarial_limites.py` · **Medido em:** 20260925, HANDOFF 05 Etapa 4
**Causa raiz:** `Modelo._matriz` só checa forma e finitude (SPEC P5)
**Impacto na planta:** nenhuma validação no ponto de serving — a lição do `mode='serve'` da aula 3
**Teste que o mata:** `test_leitura_fisicamente_impossivel_e_rejeitada_antes_da_inferencia`

### O vermelho, antes de qualquer marker

```
AssertionError: o ponto de serving aceitou leitura fisicamente impossível e emitiu
decisão: temperatura_c=500.0 (faixa da ficha: 45.0–95.0 °C) → probabilidade 0.429606;
         pressao=-3.0 (faixa da ficha: 3.0–4.5 bar) → probabilidade 0.048447
```

Um termopar em curto reporta 500 °C. A ficha técnica declara 45–95 °C e o SUT **tem** a
ficha — ela está no README dele. O que ele não tem é uma chamada de validação entre a
leitura e a inferência. O painel exibe `0.429606` ao operador como se fosse medição.

### O terceiro caso é pior, e por isso não entra neste assert

`rpm = 0` não produz probabilidade errada: produz **silêncio**. `limpar` descarta a linha
(`rpm >= 1.0`) e o lote passa de 96 para 95 linhas sem registro. O motor simplesmente some
do painel. Isso é D05, já catalogado no Bloco A, e é citado aqui porque os dois defeitos
compõem: uma leitura impossível ou é aceita como verdade, ou faz o motor desaparecer —
nunca gera alarme.

**Patch:** não. A recomendação (validar contra a ficha no ponto de serving) vai no
`relatorio.md`.

---

## D16 (casos-limite) — o reenvio do historiador dobra o peso na janela

**Onde:** `tests/test_adversarial_limites.py` · **Medido em:** 20260925, HANDOFF 05 Etapa 4
**Teste que o mata:** `test_lote_com_leitura_duplicada_nao_dobra_o_peso_na_janela`

Segundo ângulo sobre D16 (o primeiro, no Bloco A, olha a limpeza). Aqui o que se mede é a
**propagação** da duplicata pela janela móvel.

### O vermelho, antes de qualquer marker

```
AssertionError: duplicar a leitura da hora 20 — 1 chave(s) duplicada(s) sobreviveram à
limpeza, 48 linhas viraram 49 — moveu `temp_media_6h`:
  hora 20: 64.769029 → 64.909973 (+0.140944 °C)
  hora 21: 66.240009 → 66.903845 (+0.663836 °C)
  hora 22: 65.889955 → 67.919453 (+2.029498 °C)
```

**+2,03 °C na hora 22** — o dobro do ruído declarado do sensor, e mais de cinco vezes a
menor perturbação que já vira decisões em D14. Nenhuma medição nova aconteceu: o
historiador apenas reenviou uma leitura que já tinha mandado.

A hora 23 **não** se move, e isso não é ruído do experimento: a janela é
`rolling(6, center=True)`, ou seja `[t−2, t+3]`, então a duplicata da hora 20 alcança
exatamente as horas 18 a 22. O recorte da evidência casa com a geometria da janela — que é
a mesma janela de D01.

**Patch:** não. A correção é desduplicar `(id_maquina, timestamp)` em `limpar`.

---

## D24 ★ — `turno` é reetiquetagem do relógio, e mesmo assim decide

**Onde:** `tests/test_adversarial.py` · **Medido em:** 20260925, HANDOFF 06 Etapa 7
**Causa raiz:** `turno` é função determinística da hora do `timestamp` e entra em `ORDEM_FEATURES` como se fosse informação própria; a floresta a usa para separar exemplos que ela não deveria conseguir separar
**Impacto na planta:** a ordem de manutenção depende de como o relógio foi rotulado, não do motor — a mesma leitura vira alarme ou silêncio conforme a etiqueta de turno que o historiador anexou
**Teste que o mata:** `test_trocar_o_turno_nao_muda_a_decisao[1,2,3]`

`turno` é a **13ª e última** feature de `ORDEM_FEATURES`, e era a única das treze sem teste
nem exclusão justificada quando o Bloco C fechou. O `guia-do-aluno.md` encerra o bullet dos
contrafactuais perguntando **"quais campos entram nessa categoria?"** — e este é o caso em
que a resposta não depende de argumento causal nenhum: ela se mede dentro do próprio dado.

### A premissa, medida: `turno` não traz um bit novo

Tabela hora-do-dia × turno no conjunto de teste (4.200 linhas):

| hora | 0–7 | 8–15 | 16–23 |
|---|---|---|---|
| turno | **1** (175/h) | **2** (175/h) | **3** (175/h) |

```
horas com mais de um turno: 0 de 24
```

O mapeamento é uma **bijeção com o bloco de horas**. O `timestamp` já está no quadro e já é
usado para montar as janelas móveis. Portanto `turno` é o relógio com outro nome: qualquer
decisão que dependa dele depende de uma codificação redundante, não de física do motor.

Isso está no teste como **assert de premissa**, antes do oráculo. Se um dia `turno` deixar de
ser função da hora, ele pode passar a carregar informação própria — e aí o contrafactual
precisa ser redesenhado, não silenciosamente mantido.

### O vermelho, antes de qualquer marker

```
AssertionError: reetiquetar 2800 leituras para o turno 1, sem tocar em nenhum sensor e sem
mexer no timestamp, mudou: v1: 3 decisões (1↑/2↓); v2: 8 decisões (6↑/2↓). E `turno` é função
da hora do timestamp, logo não traz informação física nova. Taxa de falha por turno:
{1: 0.16, 2: 0.155, 3: 0.152857} — faixa de apenas 0.0071 (0.71 p.p.), sem confundidor que
explique a dependência

AssertionError: reetiquetar 2800 leituras para o turno 2, ... mudou: v1: 1 decisões (1↑/0↓);
v2: 10 decisões (3↑/7↓). ...

AssertionError: reetiquetar 2800 leituras para o turno 3, ... mudou: v1: 3 decisões (2↑/1↓);
v2: 9 decisões (1↑/8↓). ...
```

`3 failed, 13 deselected in 3.49s` — falha nos **três** destinos e nas **duas** versões, por
isso o `xfail` vai na função e não no `pytest.param` (a convenção fixada em D14).

### A tabela medida

| destino | linhas reetiquetadas | v1 | v2 |
|---|---:|---|---|
| turno 1 | 2.800 | 3 decisões (1↑/2↓) | 8 decisões (6↑/2↓) |
| turno 2 | 2.800 | 1 decisão (1↑/0↓) | **10** decisões (3↑/7↓) |
| turno 3 | 2.800 | 3 decisões (2↑/1↓) | 9 decisões (1↑/8↓) |

**A v2 é de novo a mais instável** — 2,7× a 10× a v1, em 3 de 3 destinos. É o **quarto** eixo
independente contra a promoção, depois do recall (D11), da varredura de limiar e da
instabilidade sob ruído (D14).

### O contraste com D06 é o que dá peso ao achado

Os dois defeitos são contrafactuais de campo que não altera o motor, e é tentador tratá-los
como o mesmo achado. Não são, e a diferença está medida:

| | D06 (`operador_senior`) | D24 (`turno`) |
|---|---|---|
| taxa de falha do grupo | **0,3988** contra 0,0794 dos outros | 0,1600 / 0,1550 / 0,1529 |
| faixa entre grupos | ~32 p.p. | **0,71 p.p.** |
| há confundidor? | **sim, forte** — a escalação do sênior é reativa à suspeita | **não** |
| posição no ranking de sensibilidade | **1ª de 13** | ver `medicoes.json → sensibilidade` |
| leitura | o modelo aprendeu um sinal real, pelo motivo errado | o modelo não tem sinal para aprender |

Em D06 a dependência é **explicável** — errada, mas explicável: o sênior de fato aparece onde
há mais falha. Em D24 não há o que explicar. Os três turnos falham praticamente igual, e a
decisão se move mesmo assim. É sobreajuste a uma coluna redundante, e é o argumento mais
limpo do bloco de contrafactuais porque não exige que ninguém aceite uma tese causal.

### Nota de desenho: o timestamp fica intacto de propósito

O contrafactual mexe **só** em `turno`, e por isso produz uma linha cujo turno não bate com a
própria hora — uma linha que a planta não emitiria. A escolha é deliberada e rende a segunda
leitura do mesmo achado: **nada no serving percebe a incoerência**, na mesma família de D21
(500 °C aceito sem validação). Um `limpar` que validasse o contrato derivaria `turno` da hora
em vez de confiar na coluna, e o defeito desapareceria junto com a feature.

**Patch:** não. Corrigir exige remover `turno` de `ORDEM_FEATURES` ou derivá-la da hora, e as
duas coisas mudam a forma da entrada do modelo — `modelo.carregar` valida a sincronia entre
`ordem_features` do artefato e `features.ORDEM_FEATURES` (SPEC P4), então qualquer uma delas
**exige retreinar**. Mesma decisão já tomada para D06, D14, D21 e D23.
