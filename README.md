# sentinela-ml-testing - suíte de testes do Sentinela (TAU, Trilha 1)

Suíte de testes automatizados para o **Sentinela**, o sistema de manutenção preditiva da Nortemec
que prevê falha de motor nas próximas 72 h. O sistema existe em duas versões - **v1** em produção e
**v2** candidata, promovida por "+3,5 pp de acurácia" - e, segundo o próprio README dele, **nunca
teve um teste**.

Esta é a suíte que ele não tinha. Ela **importa** o pacote `sentinela` e o testa de fora. Ele entra
na imagem Docker por clone no commit pinado `c9020d7ba3bb4e6fd4ae22d46346a787b16adc02`.

**O pacote sob teste não é editado**, como o enunciado exige - e isso não é para acreditar, é para
conferir. Três comandos:

```bash
git ls-files | grep -c '^src/sentinela/'                              # -> 0
grep -rc patch tests/ conftest.py | grep -v ':0$' || echo "nenhum"    # -> nenhum
docker compose run --rm suite git -C /opt/sentinela status --porcelain; echo "exit=$?"
```

O primeiro mostra que **este repositório não contém o pacote**. O segundo, que **nenhum dos 231
testes o modifica** - a suíte só importa e observa. No terceiro, o `git status --porcelain` não
imprime **nenhuma linha** e o `exit` é **0** (o compose escreve as linhas de `Container … Created`
em stderr, e elas não são saída do `git`): o clone dentro do container está idêntico ao commit
pinado depois de a suíte inteira ter rodado.

- **Relatório completo:** [`relatorio.md`](relatorio.md) - o que foi testado, por quê, e cada defeito
  nas quatro partes (teste que falha, evidência medida, causa raiz, impacto na planta).
- **Dossiê de defeitos:** [`docs/mapa-defeitos.md`](docs/mapa-defeitos.md) - o vermelho real de cada um.
- **Decisões de execução:** [`docs/decisoes.md`](docs/decisoes.md).

## Onde cada item do enunciado está

O enunciado da Trilha 1 pede três blocos de teste e três itens de entrega. Esta tabela diz, para cada
um, **qual teste responde** e **onde o relatório discute**. Os nomes são literais: dá para rodar
qualquer linha com `docker compose run --rm suite pytest -q <caminho>::<função>`.

### Bloco 1 - testes unitários do pipeline

| Item do enunciado | Teste | Relatório |
|---|---|---|
| `preprocessamento.limpar` | [`tests/test_preprocessamento.py`](tests/test_preprocessamento.py) - 13 funções | §4 |
| `features.construir` | [`tests/test_features.py`](tests/test_features.py) - 15 funções | §4 |
| tipos | `test_contrato_dados.py::test_tipos_das_colunas_batem_com_o_contrato` | §4 |
| valores faltantes | `test_contrato_dados.py::test_somente_vibracao_tem_valores_ausentes` (verde: o dropout é só de vibração) · `test_preprocessamento.py::test_vibracao_imputada_fica_na_faixa_fisica_do_sensor` **(falha: D04)** · `test_features.py::test_temperatura_ausente_nao_e_silenciosamente_imputada` **(falha: D20)** | §4, D04, D20 |
| unidades da ficha técnica | `test_preprocessamento.py::test_limpar_converte_pressao_de_psi_para_bar` · `test_contrato_dados.py::test_unidade_pressao_so_tem_valores_conhecidos` | §4, D03 |
| faixas da ficha técnica | `test_contrato_dados.py::test_{temperatura,corrente,idade_equipamento,rpm,pressao_convertida}_esta_na_faixa_da_ficha` - a ficha vive em [`suite/ficha.py`](suite/ficha.py) | §4 |
| ordem das linhas | `test_features.py::test_construir_preserva_a_ordem_de_entrada_sob_embaralhamento` · `test_construir_devolve_as_treze_colunas_na_ordem_canonica` | §4 |
| **a feature de um instante usa só leituras até aquele instante** | `test_features.py::test_temp_media_6h_nao_muda_quando_so_o_futuro_muda` **(falha: D01)**, com dois controles positivos verdes - `test_temp_max_24h_...` e `test_vib_media_6h_...` | §4, D01 |

`make unitario` roda o bloco inteiro.

### Bloco 2 - testes estatísticos

| Item do enunciado | Teste | Relatório |
|---|---|---|
| v1 × v2 **com incerteza** (bootstrap **e** McNemar) | `test_estatistico_v1_v2.py::test_intervalo_pareado_da_diferenca_de_recall_nao_contem_zero` · `::test_mcnemar_exato_acusa_diferenca_entre_v1_e_v2` · `::test_mcnemar_concorda_com_o_intervalo_pareado` | **§5.1** |
| métricas adequadas a **classe rara** | `::test_acuracia_nao_separa_a_versao_boa_da_ruim` · `::test_pr_auc_da_v2_nao_e_pior_que_a_da_v1` · `::test_f2_favorece_a_versao_com_mais_recall` · `::test_acuracia_do_preditor_sempre_zero_e_a_linha_de_base_honesta`. PR-AUC, F-beta e recall@precisão mínima em [`suite/metricas.py`](suite/metricas.py) | §5.1, D11 |
| o limiar de decisão | `test_estatistico_limiar_calibracao.py::test_varredura_de_limiar_cobre_precisao_e_recall` · `::test_limiar_0_5_maximiza_f2` · `::test_limiar_de_custo_minimo_e_0_5` · `::test_recall_com_precisao_minima_existe_para_a_v1` | **§5.2** |
| a calibração das probabilidades | `test_estatistico_limiar_calibracao.py::test_brier_da_v1_e_da_v2` · `::test_ece_por_versao_fica_abaixo_de_cinco_pontos` · `::test_curva_de_confiabilidade_e_monotona` · `::test_probabilidade_media_prevista_bate_com_a_frequencia_observada_por_faixa` | **§5.3** |
| distribuições **entre teste e produção** | [`tests/test_estatistico_drift.py`](tests/test_estatistico_drift.py) - 7 funções: diferença de médias, KS e PSI juntos (`::test_media_da_temperatura_nao_acusa_drift_entre_teste_e_producao` contra `::test_ks_acusa_drift_na_temperatura`) | **§5.4** |

`make estatistico` roda o bloco inteiro.

### Bloco 3 - testes adversariais

| Item do enunciado | Teste | Relatório |
|---|---|---|
| perturbações **menores que o ruído do sensor** | `test_adversarial.py::test_perturbacao_menor_que_o_ruido_do_sensor_nao_muda_a_decisao` **(falha: D14)** · `::test_taxa_de_flip_cresce_com_a_amplitude` · `::test_v2_nao_e_mais_instavel_que_a_v1` | **§6.1** |
| campos que não deveriam mudar a decisão (**contrafactuais**) | `test_adversarial.py::test_trocar_o_operador_senior_nao_muda_a_decisao` **(D06)** · `::test_trocar_o_turno_nao_muda_a_decisao` **(D24)** · `::test_converter_a_pressao_para_a_outra_unidade_nao_muda_a_decisao` · `::test_dropout_de_vibracao_nao_muda_as_decisoes_da_janela`. Controle positivo: `::test_mudanca_fisica_real_de_temperatura_muda_a_decisao` | **§6.2** |
| casos-limite | [`tests/test_adversarial_limites.py`](tests/test_adversarial_limites.py) - 7 funções: um motor só, lote de uma linha, lote vazio, valores idênticos, leitura impossível, duplicata, `::test_painel_de_um_registro_concorda_com_o_lote` **(D15)** | **§6.3** |

`make adversarial` roda o bloco inteiro.

### Os três itens de entrega

| Item do enunciado | Onde |
|---|---|
| repositório organizado, **com instruções de como rodar** | os seis passos abaixo |
| **a suíte rodando**, com log de execução na própria entrega | [§ O log da suíte rodando](#o-log-da-suíte-rodando) - `170 passed, 61 xfailed`, exit 0, colado de [`evidencias/log-suite.txt`](evidencias/log-suite.txt); e o vermelho, `61 failed`, exit 1 |
| documentar a detecção de **ao menos uma falha** | 24 defeitos, D01 a D24, cada um com teste que falha e número medido: [`relatorio.md`](relatorio.md) §7 e [`docs/mapa-defeitos.md`](docs/mapa-defeitos.md) |

**Os três blocos somam 98 das 123 funções** - 51 no Bloco 1, 30 no Bloco 2, 17 no Bloco 3
([`relatorio.md`](relatorio.md) §2). As outras **25** não entram nos blocos e existem para sustentar
quem entra: reprodutibilidade do ambiente (5), propriedades com `hypothesis` (6) e os testes dos
**nossos próprios** helpers (14). Esses 14 são a resposta a "como sei que a sua McNemar está certa?":
sem `scikit-learn` nem `statsmodels`, PR-AUC, F-beta, bootstrap, McNemar, Brier, ECE, PSI e KS são
código nosso, e [`tests/test_suite_interna.py`](tests/test_suite_interna.py) os confere contra casos
calculados à mão e contra o F1 do próprio SUT.

---

## Passo a passo - do clone ao relatório

**Siga daqui, na ordem.** Seis passos, cada um com o comando, o **resultado esperado literal** e
quanto leva. Os números de resultado saem dos logs em [`evidencias/`](evidencias/), não de memória.
O material de referência (alvos do Makefile, estrutura, fallback de rede) vem **depois**.

Tempo total, com a imagem já construída: **cerca de 1 min 15 s.**

---

### Passo 1 - Pré-requisitos

```bash
docker --version && docker compose version
df -h . | tail -1
```

**Resultado esperado:** duas versões impressas, sem erro, e **ao menos 3 GB livres**. Referência do
ambiente em que os números deste README foram medidos: `Docker version 29.7.1`,
`Docker Compose version v5.3.1`.

É preciso **rede** no Passo 3: o build clona o sistema sob teste do GitHub e instala do PyPI. Sem
rede, veja *Se a rede não estiver disponível*, mais abaixo.

`make` é opcional: todo passo tem a forma `docker compose`. Confira o seu `uid`, que o Passo 3 usa:

```bash
id -u && id -g
```

**Resultado esperado:** dois números, normalmente `1000` numa instalação Ubuntu ou Debian. Guarde-os
- se forem diferentes de `1001`, o Passo 3 **precisa** recebê-los, senão a suíte falha ao escrever
em `evidencias/`.

**Tempo:** instantâneo.

---

### Passo 2 - Clonar e entrar

```bash
git clone https://github.com/golympio/sentinela-ml-testing
cd sentinela-ml-testing
ls
```

**Resultado esperado:** `Cloning into 'sentinela-ml-testing'...` e o `ls` mostrando `Dockerfile`,
`docker-compose.yml`, `Makefile`, `tests/`, `suite/`, `evidencias/`, `relatorio.md`.

**Tempo:** poucos segundos.

---

### Passo 3 - Construir a imagem

São **dois comandos**: um constrói, o outro confere o que foi construído.

```bash
SUITE_UID=$(id -u) SUITE_GID=$(id -g) docker compose build 2>&1 | tail -5
```

**Resultado esperado:** o build imprime muita coisa; o `tail -5` mostra só o fim, que são cinco
linhas iguais, uma por serviço do compose:

```
 Image sentinela-ml-testing:local Built
 Image sentinela-ml-testing:local Built
 Image sentinela-ml-testing:local Built
 Image sentinela-ml-testing:local Built
 Image sentinela-ml-testing:local Built
```

`SUITE_UID` e `SUITE_GID` constroem a imagem com o **seu** usuário. Sem eles o build usa o default
`1001` e, se o seu `uid` for outro, a suíte falha ao escrever em `evidencias/` no Passo 4. Com
`make build` isso já vai junto.

> Por que não `UID=$(id -u)`: em bash `UID` é variável especial, **readonly e não exportada**, então
> ela nunca chegaria ao Docker - o build cairia no default sem avisar. Por isso o nome é `SUITE_UID`.

Agora confira que a imagem tem o sistema sob teste certo dentro dela:

```bash
docker compose run --rm suite python scripts/smoke.py; echo "exit=$?"
```

**Resultado esperado:** exatamente esta linha, e `exit=0`:

```
smoke ok: 1.0.0 | features: 13 | manifest: D23 (4 divergências conhecidas, 0 inesperadas)
exit=0
```

A versão do sistema sob teste é **1.0.0**, ele expõe **13 features**, e o manifest traz **4
divergências conhecidas e 0 inesperadas**. Este comando **não depende de cache**: roda o smoke na
hora, com a saída limpa, e é ele que você deve usar para conferir.

> **`manifest: D23` não é erro do seu ambiente.** O sistema sob teste vem de fábrica com o
> `artefatos/manifest.json` desatualizado - é o defeito **D23**, um dos 24 que esta suíte documenta.
> O smoke tolera exatamente essas quatro e **aborta o build** se aparecer uma quinta, que aí sim
> seria sinal de clone corrompido. Essa proteção continua dentro do `Dockerfile`; o comando acima só
> deixa você ver o resultado dela quando quiser.
>
> **Por que não procurar `smoke ok` na saída do build.** O Docker só executa - e só imprime - a
> camada do smoke quando ela **não** está em cache. Se a sua máquina já construiu esta imagem antes,
> o build reusa a camada, a linha não sai, e um `grep` nela devolve nada com código 1. Não é falha:
> é o cache funcionando. Por isso a conferência é um comando próprio, e não um `grep` no log.
>
> Se você usa `make`, `make build` faz o mesmo que o primeiro comando.
>
> **Se o build falhar**, repita sem o `tail -5` para ver a mensagem inteira, e consulte
> *[Se algo der errado](#se-algo-der-errado)* - as duas causas comuns são falta de rede para clonar
> o SUT e para alcançar o PyPI.

**Tempo:** **alguns minutos** na primeira vez de verdade (clone do SUT + instalação das
dependências). Com o cache de camadas do Docker, **~20 s**; sem nenhuma mudança, **~2 s**.

---

### Passo 4 - Rodar a suíte (é o comando da entrega)

```bash
docker compose run --rm suite; echo "exit=$?"
```

**Resultado esperado:** o cabeçalho confirma que você está testando a coisa certa - estas são as
primeiras dez linhas, na ordem em que saem:

```
============================= test session starts ==============================
platform linux -- Python 3.12.14, pytest-9.1.1, pluggy-1.6.0
SUT: /opt/sentinela @ c9020d7ba3bb4e6fd4ae22d46346a787b16adc02 (sentinela 1.0.0)
versões: numpy=2.5.3 pandas=2.3.3 pytest=9.1.1 scipy=1.18.1
SUITE_SEED=42 SUITE_N_BOOT=1000
rootdir: /trabalho
configfile: pyproject.toml
testpaths: tests
plugins: hypothesis-6.168.1
collected 231 items
```

- e a última linha do pytest é

```
170 passed, 61 xfailed in 30.82s
exit=0
```

O tempo varia com a máquina; **o que não varia são os números**: `collected 231 items`,
`170 passed`, `61 xfailed`, `exit=0` e **zero** ocorrências de `FAILED` ou `ERROR`.

> **`SUITE_N_BOOT=1000` aqui, `2000` no log oficial.** Este passo roda com 1000 reamostragens, que é
> o default do serviço `suite`. O log colado em [§ O log da suíte rodando](#o-log-da-suíte-rodando) e
> os números do relatório vêm de `make evidencias`, que roda com **2000**. Os dois concordam em
> `170 passed, 61 xfailed`; a linha do `SUITE_N_BOOT` é a única que difere, e é esperado.

> **⚠ Este passo regrava `evidencias/medicoes.json`.** Ao fim da sessão o `conftest.py` grava as
> medições, e com `n_boot=1000` em vez dos 2000 da evidência oficial - o sha256 do arquivo muda de
> `681d1ae6…` para `278d8eb7…` e deixa de bater com o que o cabeçalho do relatório afirma. **Não é
> defeito: é o passo funcionando.** Para devolver o clone ao estado da entrega, quando terminar:
>
> ```bash
> git checkout -- evidencias/          # descarta as medições desta rodada
> # ou, para regerar os sete artefatos de verdade (mais lento, ~2 min):
> make evidencias
> ```
>
> Confira com `sha256sum evidencias/medicoes.json`. **Não apague `evidencias/`** - os sete arquivos
> dali são parte da entrega.

> **Os 61 `xfailed` são os defeitos, não falhas da suíte.** Cada um carrega
> `xfail(strict=True)` e um motivo que começa com o ID. No fim do log eles aparecem assim:
>
> ```
> XFAIL tests/test_features.py::test_temp_media_6h_nao_muda_quando_so_o_futuro_muda
>   D01 - `rolling(6, center=True)` faz a janela ser [t-2, t+3]: a feature de agora usa
>   leitura que a planta só terá em 3 h
> ```
>
> Leia como *"este teste falhou, era esperado que falhasse, e o motivo é o defeito D01"*.
> **A suíte verde é o resultado correto.**

**Tempo:** ~40 s.

---

### Passo 5 - Ver o log vermelho, que é o que prova os defeitos

```bash
docker compose run --rm defeitos; echo "exit=$?"
```

**Resultado esperado:**

```
61 failed, 170 deselected in 10.97s
exit=1
```

**O `exit=1` é o resultado certo - este passo tem de falhar.**

Por quê: o enunciado pede que cada defeito seja documentado com *um teste que falha*. Mas uma suíte
que termina vermelha é indistinguível de uma suíte quebrada, e não serve como entrega. A solução são
**dois comandos sobre os mesmos testes**:

| Comando | O que faz com os testes de defeito | Sai |
|---|---|---|
| Passo 4, `suite` | a falha é **esperada** (`xfail`), vira `XFAIL` e não derruba nada | **0** |
| Passo 5, `defeitos` | roda com `--runxfail`, que **desliga** a marca: falham de verdade, com o `assert` e o número medido | **1** |

Para ver um defeito isolado - o vazamento temporal, o mais central deles:

```bash
docker compose run --rm suite pytest --runxfail -q \
  tests/test_features.py::test_temp_media_6h_nao_muda_quando_so_o_futuro_muda
```

**Resultado esperado:** falha, com o número medido:

```
AssertionError: temp_media_6h[t=20] mudou 3.3333 °C ao perturbar APENAS t+1..t+123
em +10.0 °C; 29 linhas do lote mudaram no total
```

**Tempo:** ~13 s.

---

### Passo 6 - Abrir o relatório

```bash
less relatorio.md      # ou abra no editor
```

**Resultado esperado:** o relatório abre com o cabeçalho de procedência (SHA do SUT, contagem da
suíte, sha256 do `medicoes.json`). **O que olhar primeiro, nesta ordem:**

| Onde | O que responde |
|---|---|
| **§1 Resumo executivo** | o veredito sobre promover a v2, em uma tela - e o que o relatório **não** conclui |
| **§5.1** | a comparação v1 × v2 com incerteza: IC pareado, McNemar, e o `n01 = 0` |
| **§6.2** | a tabela que responde *"quais campos não deveriam mudar a decisão?"* |
| **§7** | o catálogo dos 24 defeitos, cada um nas quatro partes |
| **§9** | os seis oráculos que passaram na primeira tentativa e tiveram de ser refeitos |

Em uma frase: **os +3,5 pp de acurácia da v2 reproduzem (+3,48 pp) e a decisão de promovê-la
mesmo assim é errada** - com prevalência de ~15 %, um modelo que nunca prevê falha já acerta
84,40 %.

**Tempo:** a leitura que você quiser.

---

## Se algo der errado

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| `ERRO: o clone do SUT falhou; build abortado.` | **sem rede**, ou GitHub inacessível | use um espelho: `SENTINELA_REPO=/caminho/para/espelho docker compose build`; ou carregue uma imagem exportada (veja *Se a rede não estiver disponível*) |
| `Could not fetch URL https://pypi.org/...` no build | sem rede para o PyPI | mesma saída acima; o build precisa de rede uma única vez |
| **`61 failed` e `exit=1` no Passo 5** | **nada - é o esperado** | esse alvo **tem** de sair 1: é o log vermelho da entrega. Veja a tabela do Passo 5 |
| `PermissionError … '/trabalho/evidencias/medicoes.json'` no Passo 4 ou 5 | **a imagem foi construída com um uid diferente do seu.** `evidencias/` é um bind mount: o usuário do container precisa ter o mesmo uid do seu usuário no host | reconstrua passando o seu uid: `SUITE_UID=$(id -u) SUITE_GID=$(id -g) docker compose build`, ou simplesmente `make build`. **Não apague `evidencias/`** - os sete arquivos dali são parte da entrega |
| arquivos de `evidencias/` com dono `root` (`stat -c '%u' …` devolve `0`) | algum `docker compose run` criou o diretório antes do primeiro build com uid correto | `sudo chown -R $(id -u):$(id -g) evidencias` e reconstrua como acima. Também aqui: **não apague o diretório**, só corrija o dono |
| `permission denied while trying to connect to the Docker daemon` | seu usuário não está no grupo `docker` | `sudo usermod -aG docker $USER` e reabra a sessão |
| `make: command not found` | `make` não instalado | não é obrigatório: todo passo acima tem a forma `docker compose`, desde que você passe `SUITE_UID`/`SUITE_GID` no Passo 3. Se quiser os alvos: `sudo apt-get install -y --no-install-recommends make` |
| `ERRO: o SUT nao esta no commit pinado` | o upstream mudou de HEAD | o SHA está fixo no `docker-compose.yml` e **não deve ser alterado** - é ele que torna os números reproduzíveis |
| `smoke ok: … manifest:` com número **diferente de 4** | o sistema sob teste mudou de conteúdo | **pare e investigue**: a suíte foi calibrada contra as 4 divergências conhecidas de D23 |
| algum teste vira `XPASS` e a suíte fica **vermelha** | alguém **corrigiu** um defeito | é o alarme funcionando (`xfail` é estrito). Atualize `docs/mapa-defeitos.md` e remova o marker |
| a suíte demora demais | primeira execução, ou máquina lenta | `docker compose run --rm suite pytest -m "not lento"` fecha em ~19 s |
| `docker compose` não existe, só `docker-compose` | Compose v1 | atualize para o plugin v2+; os arquivos usam sintaxe v2 |

Nenhum passo publica porta, escreve fora do diretório do projeto, ou precisa de `sudo` (exceto os
casos de permissão acima).

---

# Referência

O que vem daqui para baixo é consulta, não sequência.

## Os alvos do Makefile

| Comando | O que faz | Sai |
|---|---|---|
| `make build` | constrói a imagem (clona o SUT no SHA pinado) | 0 |
| `make suite` | **a suíte completa** - o comando de entrega | **0** |
| `make defeitos` | só os testes de defeito, com `--runxfail`: cada um **falha de verdade**, mostrando o número medido | **1**, de propósito |
| `make evidencias` | regenera **os sete artefatos juntos**, com `SUITE_N_BOOT=2000`. **Rode-o por último** - veja o aviso abaixo | 0 |
| `make correcoes` | **anexo, fora do que o enunciado pede**: aplica os patches a um clone descartável e imprime a tabela antes/depois | 0 |
| `make rapido` | exclui os testes `lento` (orçamento de 60 s) | 0 |
| `make unitario` / `estatistico` / `adversarial` | só o bloco obrigatório correspondente | 0 |
| `make lento` | só os testes caros (200 sementes, sensibilidade por feature) | 0 |
| `make colecao` | lista os testes coletados sem executá-los | 0 |
| `make limpar` | remove caches e containers parados (**não** apaga `evidencias/`) | 0 |

### O `make defeitos` sai 1, e isso é o esperado

A suíte verde marca cada teste de defeito com `xfail(strict=True)`: o defeito é conhecido, está
documentado, e a suíte continua verde. O alvo `defeitos` roda os mesmos testes com `--runxfail`,
que **desliga** o `xfail` e os faz falhar de verdade - é o log vermelho da entrega, com o número
medido em cada assert. Os dois logs fazem parte do que se entrega:
`evidencias/log-suite.txt` (exit 0) e `evidencias/log-defeitos.txt` (exit 1).

Como o `xfail` é **estrito**, se alguém corrigir um defeito o teste vira `XPASS` e **derruba a
suíte** - o aviso de que o catálogo ficou obsoleto.

### As correções propostas - **fora do que o enunciado pede**

O enunciado da Trilha 1 pede três blocos de teste, instruções de execução, o log da suíte e ao menos
uma falha documentada. **Ele não pede correção nenhuma** - e a regra que ele dá é a oposta: *"não
editem o pacote sentinela; defeito encontrado se documenta com um teste que falha"*.

Então isto é **anexo, não entrega**. Os seis passos acima não passam por aqui, e **nenhum dos 231
testes** depende de um patch: a suíte inteira roda contra o clone intacto. O que o anexo responde é
uma pergunta que veio depois de os defeitos estarem provados - *e se a gente corrigisse?* - e a
resposta foi útil o suficiente para ficar registrada.

```bash
docker compose run --rm correcoes; echo "exit=$?"
```

`3 patches aplicados`, os quatro testes-alvo passando, `exit=0`, e a tabela:

```
  versão  métrica           antes       depois   Δ (depois−antes)
  ---------------------------------------------------------------
  v1      pr_auc         0.581091     0.605164          +0.024073
  v1      custo              1765         1806                +41
  v2      pr_auc         0.671808     0.696078          +0.024270
  v2      custo              4393         4355                -38
```

Os patches corrigem D01 (vazamento temporal), D02 (vazamento de alvo) e D03 (unidade de pressão).
São aplicados com `git apply` ao clone **dentro de um container descartável**, que
[`scripts/correcoes.sh`](scripts/correcoes.sh) reverte com `git checkout -- .` e confere com
`status --porcelain` antes de sair. O script **aborta** se o clone já estiver sujo ao começar, e
redireciona `SUITE_MEDICOES` para `/tmp` para que as medições do sistema corrigido não contaminem
`evidencias/medicoes.json`. Nada disso alcança o host, e este repositório nunca contém o pacote.

**O que a tabela mostra:** a PR-AUC sobe nas duas versões (+2,41 pp e +2,43 pp) - com a entrada
honesta, os modelos ranqueiam melhor - **e o custo da v1 piora** (1.765 → 1.806), porque o limiar
`0.5` estava afinado para a entrada defeituosa. Os modelos foram treinados *com* os defeitos
presentes, então corrigir a entrada sem retreinar entrega ao modelo uma distribuição que ele nunca
viu. É o mesmo argumento de D11 por outro caminho: **o limiar é parte do modelo, não uma constante.**

### `evidencias/medicoes.json` é regravado por qualquer rodada - rode `make evidencias` por último

Todo `docker compose run --rm suite ...` grava `evidencias/medicoes.json` ao fim da sessão. O
serviço `suite` roda com `SUITE_N_BOOT=1000`; o alvo `evidencias`, com **2000**. Então uma rodada
avulsa **substitui** os números da evidência oficial pelos de outra configuração.

Não é perda de dado - é perda de **procedência**, e por isso o próprio arquivo a registra:

```bash
grep -o '"n_boot": [0-9]*' evidencias/medicoes.json
#  "n_boot": 2000   <- conjunto oficial
#  "n_boot": 1000   <- sobrescrito por uma rodada avulsa

sha256sum evidencias/medicoes.json
#  681d1ae6…  <- o conjunto oficial, que o relatório cita
#  278d8eb7…  <- o que uma rodada do Passo 4 produz
```

> `grep` e `sha256sum` são usados aqui de propósito, para o comando não depender de você ter `python`
> no host - em Ubuntu e Debian só existe `python3`. Se preferir ver o bloco inteiro:
> `python3 -c "import json;print(json.load(open('evidencias/medicoes.json'))['sut'])"`.

Se `n_boot` não for 2000, há dois caminhos:

```bash
git checkout -- evidencias/    # instantâneo: devolve os artefatos da entrega
make evidencias                # ~2 min: regera os sete da mesma execução
```

O primeiro serve quando você só rodou a suíte e quer o clone de volta ao estado publicado. O segundo,
quando você mudou algo e quer números novos e coerentes entre si. É o conjunto que o relatório cita.

### Se a rede não estiver disponível

O `docker build` precisa de rede para clonar o SUT e instalar as dependências. Alternativas:

```bash
# espelho local do SUT
SENTINELA_REPO=/caminho/para/espelho docker compose build

# ou a imagem já construída, exportada de outra máquina
docker save sentinela-ml-testing:local | gzip > entrega-sentinela.tar.gz
docker load < entrega-sentinela.tar.gz
```

> A imagem é construída para a arquitetura local. O host de desenvolvimento é **arm64**; em x86 o
> build refaz a imagem em vez de reusar um `docker save`.

## Estrutura

```
sentinela-ml-testing/
  Dockerfile              clona o SUT no SHA pinado; aborta se o SHA divergir ou o clone falhar
  docker-compose.yml      5 serviços: suite, defeitos, correcoes, evidencias, shell
  Makefile                os alvos acima
  requirements.txt        dependências pinadas com ==
  pyproject.toml          markers registrados, --strict-markers, xfail_strict
  conftest.py             sementes, fixtures de sessão, isolamento do estado global do SUT
  suite/                  os nossos helpers (não são testes)
    ficha.py              a ficha técnica dos sensores como contrato executável
    fabrica.py            lotes sintéticos determinísticos
    harness.py            prever COM e SEM vazamento de alvo
    metricas.py           PR-AUC, F-beta, recall@precisão mínima
    estatistica.py        bootstrap pareado, McNemar exato, estabilidade do veredito
    calibracao.py         Brier, ECE, curva de confiabilidade
    drift.py              diferença de médias, KS, PSI
    perturbacao.py        ruído controlado, contrafactuais, taxa de flip
  tests/                  14 arquivos, 123 funções, 231 ids
  scripts/                smoke do build, linha de base, evidências, correções
  patches/                anexo fora do escopo do enunciado: as correções propostas (D01, D02, D03)
  evidencias/             os artefatos de saída (logs, junit, linha de base, medições)
  docs/                   mapa de defeitos e decisões de execução
```

## O log da suíte rodando

Saída real, colada de [`evidencias/log-suite.txt`](evidencias/log-suite.txt). O arquivo é gerado por
`make evidencias`, por isso a linha do `SUITE_N_BOOT` diz **2000** e não os 1000 do Passo 4 - o resto
é idêntico:

```
============================= test session starts ==============================
platform linux -- Python 3.12.14, pytest-9.1.1, pluggy-1.6.0
SUT: /opt/sentinela @ c9020d7ba3bb4e6fd4ae22d46346a787b16adc02 (sentinela 1.0.0)
versões: numpy=2.5.3 pandas=2.3.3 pytest=9.1.1 scipy=1.18.1
SUITE_SEED=42 SUITE_N_BOOT=2000
rootdir: /trabalho
configfile: pyproject.toml
testpaths: tests
plugins: hypothesis-6.168.1
collected 231 items

tests/test_adversarial.py xxx..xxx.xxxxxx.                               [  6%]

[...]

XFAIL tests/test_features.py::test_temp_media_6h_nao_muda_quando_so_o_futuro_muda
  D01 - `rolling(6, center=True)` faz a janela ser [t-2, t+3]: a feature de agora usa
  leitura que a planta só terá em 3 h
XFAIL tests/test_vazamento_alvo.py::test_maquina_risco_nao_depende_do_rotulo_do_proprio_lote
  D02 - a feature é a média de `falha_72h` do grupo quando a coluna está presente

======================= 170 passed, 61 xfailed in 31.09s =======================
exit=0
```

E o vermelho, de `make defeitos`
([`evidencias/log-defeitos.txt`](evidencias/log-defeitos.txt)):

```
E   AssertionError: temp_media_6h[t=20] mudou 3.3333 °C ao perturbar APENAS t+1..t+123
    em +10.0 °C; 29 linhas do lote mudaram no total

===================== 61 failed, 170 deselected in 10.97s ======================
exit=1
```

## O que a suíte encontrou, em uma tela

**24 defeitos**, D01 a D24, cada um com um teste que falha e um número medido. Os cinco que
carregam o relatório:

| ID | Achado | Número |
|---|---|---|
| **D01** | vazamento **temporal**: `rolling(6, center=True)` faz a janela ser `[t−2, t+3]` | `temp_media_6h[t=20]` muda **3,3333 °C** ao perturbar **só** o futuro |
| **D02** | vazamento de **alvo**: `maquina_risco` é recalculada a partir do rótulo | PR-AUC da v1 no teste infla **+28,68 pp**; a feature chega a 0,428571 contra teto de 0,214286 |
| **D11** | a promoção da v2 foi decidida por acurácia | IC pareado do Δrecall **[0,2069; 0,2704]** ⇒ v1 melhor; McNemar `p = 1,1e-47`; **`n01 = 0`** |
| **D14** | a decisão muda **dentro do erro do sensor** | a ±0,1 °C - um décimo do ruído declarado - a v1 vira **12** decisões e a v2, **18** |
| **D06** | o modelo lê **quem estava de plantão** | trocar OP-07 por OP-03 com sensores bit-idênticos apaga **57** e **155** alarmes, todos para baixo |

O veredito sobre a v2 está em [`relatorio.md`](relatorio.md), e não é "a v2 é ruim" - é que a
decisão foi tomada com o instrumento errado.

**Parte do sistema está correta, e isso também é resultado:** 170 testes passam. Uma suíte só
vermelha não distingue sinal de ruído.

---

Trabalho da disciplina **TAU - Testes Automatizados para Modelos de IA**, pós-graduação em
Engenharia de Inteligência Artificial e MLOps, PUC Minas. Trilha 1 (ML clássico).
Sistema sob teste: <https://github.com/felipehp/sentinela-nortemec> @ `c9020d7`.
