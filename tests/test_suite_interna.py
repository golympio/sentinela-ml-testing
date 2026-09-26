"""A suíte testando o próprio ferramental (bloco M).

Um validador que nunca levanta, ou uma fábrica que não é determinística, produziria
testes verdes que não provam nada. Estes testes existem para que o resto da suíte
possa ser levado a sério.
"""
from __future__ import annotations

import numpy as np
import pytest
from scipy.stats import binomtest, ks_2samp

import sentinela as sn
from suite import calibracao, drift, estatistica, fabrica, ficha, harness, metricas

pytestmark = [pytest.mark.meta, pytest.mark.rapido]


def _lote():
    return fabrica.lote(n_maquinas=2, n_horas=24, seed=42)


# (nome, chamada que passa, chamada que falha, trecho esperado na mensagem)
CASOS = [
    (
        "validar_schema",
        lambda df: ficha.validar_schema(df, ("temperatura_c", "rpm")),
        lambda df: ficha.validar_schema(df.drop(columns=["rpm"]), ("temperatura_c", "rpm")),
        "rpm",
    ),
    (
        "validar_faixa",
        lambda df: ficha.validar_faixa(df, "temperatura_c"),
        lambda df: ficha.validar_faixa(
            fabrica.com_leitura_fora_de_faixa(df, "temperatura_c", 500.0), "temperatura_c"
        ),
        "temperatura_c",
    ),
    (
        "validar_sem_faltantes",
        lambda df: ficha.validar_sem_faltantes(df, "temperatura_c"),
        lambda df: ficha.validar_sem_faltantes(
            df.assign(temperatura_c=df["temperatura_c"].mask(df.index == 0)), "temperatura_c"
        ),
        "temperatura_c",
    ),
    (
        "validar_chave_unica",
        lambda df: ficha.validar_chave_unica(df),
        lambda df: ficha.validar_chave_unica(fabrica.com_leitura_duplicada(df)),
        "id_maquina",
    ),
    (
        "validar_unidade_pressao",
        lambda df: ficha.validar_unidade_pressao(df),
        lambda df: ficha.validar_unidade_pressao(df.assign(unidade_pressao="kgf/cm2")),
        "unidade_pressao",
    ),
    (
        "validar_id_operador",
        lambda df: ficha.validar_id_operador(df),
        lambda df: ficha.validar_id_operador(df.assign(id_operador="OP-99")),
        "id_operador",
    ),
    (
        "validar_dominio",
        lambda df: ficha.validar_dominio(df, "turno", ficha.TURNOS),
        lambda df: ficha.validar_dominio(df.assign(turno=4), "turno", ficha.TURNOS),
        "turno",
    ),
    (
        "validar_completude",
        lambda df: ficha.validar_completude(df, "temperatura_c", 1.0),
        lambda df: ficha.validar_completude(
            fabrica.com_dropout_de_vibracao(df, fracao=0.5, seed=1), "vibracao_rms", 1.0
        ),
        "vibracao_rms",
    ),
]

IDS = [caso[0] for caso in CASOS]


@pytest.mark.parametrize("passa", [c[1] for c in CASOS], ids=IDS)
def test_validador_retorna_true_quando_passa(passa):
    """Padrão da aula 3: o validador devolve `True`, não `None`."""
    assert passa(_lote()) is True


@pytest.mark.parametrize(
    "falha,trecho", [(c[2], c[3]) for c in CASOS], ids=IDS
)
def test_validador_levanta_value_error_nomeando_a_coluna(falha, trecho):
    """Não basta levantar: a mensagem precisa dizer **onde** está o problema."""
    with pytest.raises(ValueError, match=trecho):
        falha(_lote())


def test_fabrica_e_determinista_por_semente():
    """Mesma semente, mesmo lote; sementes diferentes, lotes diferentes (S13)."""
    assert fabrica.lote(seed=7).equals(fabrica.lote(seed=7))
    assert not fabrica.lote(seed=7).equals(fabrica.lote(seed=8))

    com_psi = fabrica.com_linhas_em_psi(fabrica.lote(seed=7), seed=3)
    assert com_psi.equals(fabrica.com_linhas_em_psi(fabrica.lote(seed=7), seed=3))


def test_lote_da_fabrica_atravessa_o_pipeline():
    """Se a fábrica não produz lote válido, todo teste que a usa é inconclusivo."""
    saida = sn.pipeline.executar(fabrica.lote(n_maquinas=3, n_horas=48, seed=42))

    assert len(saida) == 144
    assert {"id_maquina", "timestamp", "probabilidade", "predicao"} <= set(saida.columns)
    assert saida["probabilidade"].between(0.0, 1.0).all()
    assert set(saida["predicao"].unique()) <= {0, 1}


def test_perturbar_apenas_o_futuro_nao_toca_o_passado():
    """O insumo do teste de D01 precisa ser confiável antes de acusar o SUT."""
    base = fabrica.lote(n_maquinas=2, n_horas=24, seed=42)
    hora = 10
    perturbado = fabrica.perturbar_apenas_o_futuro(base, "M01", hora, "temperatura_c", 10.0)

    do_motor = base.index[base["id_maquina"] == "M01"]
    passado = do_motor[: hora + 1]
    futuro = do_motor[hora + 1 :]

    np.testing.assert_array_equal(
        base.loc[passado, "temperatura_c"].to_numpy(),
        perturbado.loc[passado, "temperatura_c"].to_numpy(),
    )
    assert (perturbado.loc[futuro, "temperatura_c"] > base.loc[futuro, "temperatura_c"]).all()
    # o outro motor não é tocado
    outro = base.index[base["id_maquina"] == "M02"]
    np.testing.assert_array_equal(
        base.loc[outro, "temperatura_c"].to_numpy(),
        perturbado.loc[outro, "temperatura_c"].to_numpy(),
    )


# --- helpers de métrica (SPEC §4.2, nasce no HANDOFF 03) -------------------

def test_average_precision_e_fbeta_em_casos_calculados_a_mao():
    """Casos cujo valor se calcula no papel — o oráculo não pode vir da própria implementação."""
    # ranking perfeito: todos os positivos acima de todos os negativos → AP = 1,0
    assert metricas.average_precision([1, 1, 0, 0], [0.9, 0.8, 0.2, 0.1]) == pytest.approx(1.0)

    # ranking invertido: positivos por último.
    # cortes: 1/3 em recall 0,5; 2/4 em recall 1,0 → AP = 0,5·(1/3) + 0,5·(2/4) = 0,41666…
    assert metricas.average_precision([0, 0, 1, 1], [0.9, 0.8, 0.2, 0.1]) == pytest.approx(
        0.5 * (1 / 3) + 0.5 * (2 / 4)
    )

    # F2 pesa recall 4× a precisão (β²=4): 1 acerto, 1 falso positivo, 1 falso negativo
    # precisão = recall = 0,5 → F-beta = 0,5 para qualquer beta
    assert metricas.fbeta([1, 1, 0], [1, 0, 1], beta=2.0) == pytest.approx(0.5)
    # precisão 1,0 e recall 0,5: F1 = 2/3; F2 = 5·1·0,5/(4·1+0,5) = 0,5555…
    assert metricas.fbeta([1, 1, 0], [1, 0, 0], beta=1.0) == pytest.approx(2 / 3)
    assert metricas.fbeta([1, 1, 0], [1, 0, 0], beta=2.0) == pytest.approx(5 * 0.5 / 4.5)

    # sem nenhum verdadeiro positivo, F-beta é 0 por definição (e não NaN)
    assert metricas.fbeta([1, 1, 0], [0, 0, 1], beta=2.0) == 0.0


def test_fbeta_com_beta_um_concorda_com_o_f1_do_sut():
    """`fbeta(β=1)` tem de ser o mesmo F1 que `sn.avaliacao.metricas` reporta."""
    lote = fabrica.lote(n_maquinas=4, n_horas=60, seed=42)
    saida = sn.pipeline.executar(lote)
    y, pred = saida["falha_72h"].to_numpy(), saida["predicao"].to_numpy()

    assert metricas.fbeta(y, pred, beta=1.0) == pytest.approx(
        sn.avaliacao.metricas(y, pred)["f1"]
    )


def test_empates_de_score_entram_num_unico_ponto_de_corte():
    """Com 60 e 80 árvores há muitos scores iguais, e agrupar ou não muda o número.

    Quatro linhas, dois positivos, **todas com o mesmo score**: nenhum limiar consegue
    separá-las. O único corte real pega as quatro, com precisão 0,5 e recall 1,0 — logo
    AP = 0,5. Tratar empates como cortes distintos daria 0,75, desempenho que limiar nenhum
    entrega.
    """
    y = [1, 0, 1, 0]
    score = [0.7, 0.7, 0.7, 0.7]

    precisao, recall, _ = metricas.curva_precisao_recall(y, score)
    assert len(precisao) == 2, f"esperado 1 corte + âncora, obtido {len(precisao) - 1} cortes"
    assert metricas.average_precision(y, score) == pytest.approx(0.5)


def test_recall_com_precisao_minima_encontra_o_maior_corte_viavel():
    y = [1, 1, 0, 1, 0, 0]
    score = [0.9, 0.8, 0.7, 0.6, 0.5, 0.4]

    # precisão 1,0 só nos dois primeiros → recall 2/3
    recall, limiar = metricas.recall_com_precisao_minima(y, score, 1.0)
    assert recall == pytest.approx(2 / 3)
    assert limiar == pytest.approx(0.8)

    # exigência impossível devolve (0,0, inf) em vez de levantar
    assert metricas.recall_com_precisao_minima([1, 0, 0, 0], [0.4, 0.9, 0.8, 0.7], 1.0) == (
        0.0,
        float("inf"),
    )


@pytest.mark.parametrize(
    "chamada,trecho",
    [
        (lambda: metricas.average_precision([1, 1], [0.5]), "tamanhos diferentes"),
        (lambda: metricas.average_precision([0, 0], [0.5, 0.4]), "não há positivos"),
        (lambda: metricas.fbeta([1, 0], [1, 0], beta=0.0), "beta deve ser positivo"),
        (lambda: metricas.average_precision([2, 0], [0.5, 0.4]), "binário"),
    ],
)
def test_metricas_rejeitam_entrada_invalida_nomeando_o_problema(chamada, trecho):
    with pytest.raises(ValueError, match=trecho):
        chamada()


# --- incerteza: bootstrap e McNemar (SPEC §4.2, nasce no HANDOFF 04) -------
#
# Dois modelos sintéticos de qualidade CONHECIDA, em 60 linhas. O tamanho não é
# arbitrário: o registro da aula 4 mostra o veredito de significância oscilando com 20
# amostras e estabilizando com 40.

_Y_REF = np.array([1] * 30 + [0] * 30)

# recall 1,0 — acerta todos os positivos, com 6 falsos positivos
_FORTE = _Y_REF.copy()
_FORTE[30:36] = 1

# recall 0,5 — perde metade dos positivos, com os mesmos 6 falsos positivos
_FRACO = _Y_REF.copy()
_FRACO[15:30] = 0
_FRACO[30:36] = 1


def _recall(y, pred) -> float:
    return float(sn.avaliacao.metricas(y, pred)["recall"])


def _ic_contem_a_estimativa_pontual():
    pontual = _recall(_Y_REF, _FRACO)
    lo, hi = estatistica.bootstrap_ci(_Y_REF, _FRACO, _recall, n_boot=500)
    assert lo <= pontual <= hi, f"IC [{lo:.4f}, {hi:.4f}] não contém a estimativa {pontual:.4f}"
    assert lo < hi, "um IC sem largura sobre modelo imperfeito indica reamostragem quebrada"


def _predicao_perfeita_da_intervalo_degenerado_em_um():
    lo, hi = estatistica.bootstrap_ci(_Y_REF, _Y_REF, _recall, n_boot=500)
    assert (lo, hi) == (1.0, 1.0), f"esperado [1,0; 1,0], obtido [{lo}, {hi}]"


def _mesma_semente_da_o_mesmo_intervalo():
    a = estatistica.bootstrap_ci(_Y_REF, _FRACO, _recall, n_boot=500, seed=7)
    b = estatistica.bootstrap_ci(_Y_REF, _FRACO, _recall, n_boot=500, seed=7)
    assert a == b, f"mesma semente deu intervalos diferentes: {a} vs {b}"


def _pareado_com_modelos_identicos_degenera_em_zero():
    """Prova que A e B compartilham os índices.

    Com reamostragem independente o intervalo teria largura mesmo aqui, porque cada
    modelo seria medido numa amostra diferente — e a diferença é identicamente nula.
    """
    lo, hi = estatistica.bootstrap_ci_pareado(_Y_REF, _FRACO, _FRACO, _recall, n_boot=500)
    assert (lo, hi) == (0.0, 0.0), f"esperado [0,0; 0,0], obtido [{lo}, {hi}]"


def _pareado_asserta_o_lado_do_intervalo():
    """O teste que protege a convenção de sinal (SPEC §5, `docs/decisoes.md`).

    Fixar só a ordem dos argumentos não protege: quem a inverter muda o veredito do
    relatório e o intervalo continua excluindo zero — a suíte seguiria verde. Aqui se sabe
    de antemão qual modelo é melhor, então o **lado** do intervalo é verificável.
    """
    lo, hi = estatistica.bootstrap_ci_pareado(_Y_REF, _FORTE, _FRACO, _recall, n_boot=500)
    assert lo > 0, f"com a=forte, o IC [{lo:.4f}, {hi:.4f}] deveria ser inteiro positivo"
    assert estatistica.veredito(lo, hi) == "a_melhor"

    # invertido: mesmo fato, sinal trocado — e veredito trocado
    lo_i, hi_i = estatistica.bootstrap_ci_pareado(_Y_REF, _FRACO, _FORTE, _recall, n_boot=500)
    assert hi_i < 0, f"com a=fraco, o IC [{lo_i:.4f}, {hi_i:.4f}] deveria ser inteiro negativo"
    assert estatistica.veredito(lo_i, hi_i) == "b_melhor"

    assert (lo, hi) == pytest.approx((-hi_i, -lo_i)), "inverter os argumentos deve espelhar o IC"


def _mcnemar_conta_os_discordantes_e_concorda_com_binomtest():
    """`n01`/`n10` conhecidos por construção; o p conferido contra o `scipy`."""
    a, b = _Y_REF.copy(), _Y_REF.copy()
    b[0:12] = 1 - b[0:12]      # 12 linhas em que A acerta e B erra  → n10
    a[40:43] = 1 - a[40:43]    #  3 linhas em que A erra e B acerta  → n01

    n01, n10, p = estatistica.mcnemar(_Y_REF, a, b)

    assert (n01, n10) == (3, 12)
    assert p == pytest.approx(binomtest(3, 15, 0.5, alternative="two-sided").pvalue)


def _mcnemar_sem_discordancia_da_p_igual_a_um():
    """Sem discordante não há evidência de diferença — e `binomtest` com n=0 levantaria."""
    assert estatistica.mcnemar(_Y_REF, _FRACO, _FRACO) == (0, 0, 1.0)


CASOS_INCERTEZA = [
    _ic_contem_a_estimativa_pontual,
    _predicao_perfeita_da_intervalo_degenerado_em_um,
    _mesma_semente_da_o_mesmo_intervalo,
    _pareado_com_modelos_identicos_degenera_em_zero,
    _pareado_asserta_o_lado_do_intervalo,
    _mcnemar_conta_os_discordantes_e_concorda_com_binomtest,
    _mcnemar_sem_discordancia_da_p_igual_a_um,
]


@pytest.mark.parametrize(
    "caso", CASOS_INCERTEZA, ids=[c.__name__.lstrip("_") for c in CASOS_INCERTEZA]
)
def test_bootstrap_e_mcnemar_em_casos_de_referencia(caso):
    caso()


# --- calibração e drift: valores de referência (SPEC §4.2, nasce no HANDOFF 04) ---
#
# Brier, ECE e PSI são implementados por nós e sustentam os vereditos de D12 e D13. Um erro
# aqui não apareceria como teste vermelho — apareceria como conclusão errada no relatório.


def _brier_de_probabilidade_constante():
    """Com probabilidade constante `p`, o Brier tem fórmula fechada: q(1−p)² + (1−q)p².

    O oráculo vem da álgebra, não da implementação.
    """
    y = np.array([1, 1, 0, 0, 0, 0, 0, 0, 0, 0])      # prevalência q = 0,2
    p = 0.3
    esperado = 0.2 * (1 - p) ** 2 + 0.8 * p**2
    assert calibracao.brier(y, np.full(y.shape, p)) == pytest.approx(esperado)

    # previsão perfeita → 0; previsão perfeitamente invertida → 1
    assert calibracao.brier([1, 0], [1.0, 0.0]) == 0.0
    assert calibracao.brier([1, 0], [0.0, 1.0]) == 1.0


def _ece_de_probabilidade_perfeita_e_zero():
    """Quem acerta com confiança 0 ou 1 não tem desvio nenhum entre confiança e frequência."""
    y = np.array([1, 1, 0, 0])
    assert calibracao.ece(y, np.array([1.0, 1.0, 0.0, 0.0])) == pytest.approx(0.0)

    # e o oposto: confiança 1,0 em quem não falhou dá desvio máximo
    assert calibracao.ece(np.array([0, 0]), np.array([1.0, 1.0])) == pytest.approx(1.0)


def _ece_e_a_media_ponderada_dos_gaps():
    """ECE calculado no papel: duas faixas, pesos 0,5 e 0,5, gaps 0,1 e 0,3 → 0,2."""
    #  faixa 0,0–0,1: conf 0,10, 0 de 2 falham  → gap 0,10
    #  faixa 0,9–1,0: conf 0,90, 1 de 2 falham  → gap 0,40
    y = np.array([0, 0, 1, 0])
    proba = np.array([0.1, 0.1, 0.9, 0.9])
    assert calibracao.ece(y, proba, faixas=10) == pytest.approx(0.5 * 0.10 + 0.5 * 0.40)


def _psi_contra_si_mesma_e_zero():
    """A mesma série comparada consigo dá exatamente 0 — e o PSI nunca é negativo."""
    rng = np.random.default_rng(42)
    serie = rng.normal(70.0, 5.0, size=2000)

    assert drift.psi(serie, serie) == pytest.approx(0.0, abs=1e-12)

    deslocada = serie + 3.0
    assert drift.psi(serie, deslocada) > 0.0
    # simétrico na magnitude: deslocar para um lado ou para o outro mede o mesmo tamanho
    assert drift.psi(serie, serie - 3.0) > 0.0


def _psi_cresce_com_o_deslocamento():
    """Um índice de drift que não cresce com o drift não serve para classificar faixa."""
    rng = np.random.default_rng(7)
    base = rng.normal(70.0, 5.0, size=4000)
    valores = [drift.psi(base, base + d) for d in (0.5, 2.0, 5.0)]

    assert valores == sorted(valores), f"PSI não é monótono no deslocamento: {valores}"
    assert drift.classificar_psi(valores[0]) == "estavel"
    assert drift.classificar_psi(valores[-1]) == "drift"


def _ks_concorda_com_o_scipy():
    """`detectar_drift_ks` não pode divergir da referência que diz implementar."""
    rng = np.random.default_rng(3)
    a = rng.normal(0.0, 1.0, size=500)
    b = rng.normal(0.4, 1.0, size=500)

    medida = drift.detectar_drift_ks(a, b, alpha=0.01)
    referencia = ks_2samp(a, b)

    assert medida["ks_p"] == pytest.approx(float(referencia.pvalue))
    assert medida["estatistica"] == pytest.approx(float(referencia.statistic))
    assert medida["drift"] is (float(referencia.pvalue) < 0.01)


def _detectores_ignoram_nan_em_vez_de_propagar():
    """O dropout de vibração é real (D04/D20) e não é drift: NaN sai antes da conta."""
    com_nan = np.array([1.0, 2.0, np.nan, 3.0, 4.0])
    sem_nan = np.array([1.0, 2.0, 3.0, 4.0])

    assert drift.psi(com_nan, com_nan) == pytest.approx(drift.psi(sem_nan, sem_nan))
    assert np.isfinite(drift.detectar_drift_media(com_nan, sem_nan)["delta_media"])


CASOS_CALIBRACAO_DRIFT = [
    _brier_de_probabilidade_constante,
    _ece_de_probabilidade_perfeita_e_zero,
    _ece_e_a_media_ponderada_dos_gaps,
    _psi_contra_si_mesma_e_zero,
    _psi_cresce_com_o_deslocamento,
    _ks_concorda_com_o_scipy,
    _detectores_ignoram_nan_em_vez_de_propagar,
]


@pytest.mark.parametrize(
    "caso",
    CASOS_CALIBRACAO_DRIFT,
    ids=[c.__name__.lstrip("_") for c in CASOS_CALIBRACAO_DRIFT],
)
def test_brier_ece_psi_e_ks_em_valores_de_referencia(caso):
    caso()


# --- estabilidade do veredito (SPEC §4.2; antecipada do H05, ver Registro do HANDOFF 04) ---


@pytest.mark.lento
def test_veredito_estatistico_e_estavel_em_duzentas_sementes():
    """O veredito que o relatório afirma não pode depender da semente.

    É a mitigação do risco de flaky do PRD §8. Um intervalo que exclui zero em 150 de 200
    sementes não é um resultado, é um sorteio — e seria publicado como se fosse.

    `n_boot=200` aqui, e não os 1.000 do teste de verdade: o que se mede é a estabilidade do
    **veredito** sob a semente, não a precisão do intervalo. Com 200 reamostragens o
    intervalo é mais largo, o que torna esta verificação **mais** exigente, não menos — se o
    veredito sobrevive ao intervalo largo, sobrevive ao estreito.

    O marker `rapido` herdado do módulo é inerte: nenhum alvo do Makefile seleciona `-m
    rapido`, e `make rapido` roda `-m "not lento"`, que exclui este teste.
    """
    lote = sn.dados.carregar("teste")
    y, _, pred_v1 = harness.prever_sem_vazamento(lote, "v1")
    _, _, pred_v2 = harness.prever_sem_vazamento(lote, "v2")

    def recall(yy, pp):
        return float(sn.avaliacao.metricas(yy, pp)["recall"])

    def veredito_da_semente(semente: int) -> str:
        lo, hi = estatistica.bootstrap_ci_pareado(
            y, pred_v1, pred_v2, recall, n_boot=200, seed=semente
        )
        return estatistica.veredito(lo, hi)

    resultado = estatistica.estabilidade_do_veredito(veredito_da_semente, sementes=200)

    assert resultado["veredito"] == "a_melhor"
    assert resultado["concordantes"] >= 199, (
        f"o veredito oscila com a semente: {resultado['contagem']}"
    )

    # O McNemar não entra aqui de propósito: é exato e não reamostra nada, então não tem
    # semente de que depender. Só o bootstrap precisa desta prova.


def test_estado_global_do_sentinela_fica_limpo_entre_testes(request):
    """Prova que `_isola_estado_global` faz o que promete (SPEC S12, D4).

    `features._RISCO_CONGELADO` e `modelo._CACHE` são módulo-globais memoizadas na primeira
    chamada (SPEC P3). Sem isolamento, um teste contamina o seguinte — e dependência de
    ordem é a causa nº 2 de flaky no levantamento da aula 6 (Luo et al.). A fixture autouse
    do `conftest.py` zera a primeira e **vigia** a segunda; este teste é a prova de que a
    proteção está ligada, e não uma boa intenção no código.

    A prova tem três partes, e a do meio é a que vale: o teste **provoca a contaminação de
    propósito**. Se a fixture não limpasse, o próximo teste que tocasse em M01 veria um
    risco de 0,999 vindo daqui. A suíte continuar verde depois deste teste é o resultado.
    """
    # 1. Entrada limpa. No `make suite` dezenas de testes anteriores já preencheram a
    #    global; se ela chega aqui como None, é porque alguém a zerou entre um e outro.
    assert sn.features._RISCO_CONGELADO is None, (
        "`_RISCO_CONGELADO` chegou suja a este teste: o isolamento de S12 não está ativo"
    )
    assert "_isola_estado_global" in request.fixturenames, (
        "a fixture de isolamento deixou de ser autouse — S12 caiu sem ninguém notar"
    )

    # 2. E a limpeza não é trivial, porque a memoização é real e observável.
    tabela = sn.features.risco_congelado()
    assert sn.features._RISCO_CONGELADO is tabela, "o SUT deixou de memoizar a tabela"

    contaminada = dict(tabela)
    contaminada["M01"] = 0.999
    sn.features._RISCO_CONGELADO = contaminada

    uma = fabrica.lote_de_uma_linha().drop(columns=["falha_72h"])
    uma["id_maquina"] = "M01"
    X = sn.features.construir(sn.preprocessamento.limpar(uma))
    assert X["maquina_risco"].iloc[0] == 0.999, (
        "a global não alimenta mais `construir` — o risco de contaminação que S12 cobre "
        "mudou de forma, e a fixture precisa ser reavaliada"
    )

    # 3. O cache de modelo é memoizado por identidade, que é o que a fixture vigia: ela
    #    falha se um teste SUBSTITUIR um modelo já carregado. Limpá-lo custaria reparsear
    #    ~550 KB de JSON por teste, então ele é vigiado, não zerado.
    modelo = sn.modelo.carregar("v1")
    assert sn.modelo.carregar("v1") is modelo, "`modelo._CACHE` deixou de memoizar"
    assert sn.modelo._CACHE["v1"] is modelo
