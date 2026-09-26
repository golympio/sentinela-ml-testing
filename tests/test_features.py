"""`features.construir` — forma, ordem e a pergunta central do Bloco A.

*A feature de um instante usa só leituras até aquele instante?*

O oráculo é de **perturbação**, não de valor esperado: mexemos somente em `t+1, t+2, …`
e exigimos que a feature de `t` não se mexa. Isso não depende do offset da janela par do
pandas (SPEC P6), então não quebra quando a versão muda — ao contrário de comparar com
um número calculado à mão.

Ordem de leitura importa aqui: os dois **controles positivos** vêm antes do teste-estrela.
`temp_max_24h` e `vib_media_6h` usam janela sem `center` e passam. São eles que dão
autoridade ao terceiro: quando `temp_media_6h` falha no mesmo experimento, a causa é a
janela centrada, e não o experimento.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import sentinela as sn
from sentinela.features import ORDEM_FEATURES
from suite import fabrica

pytestmark = pytest.mark.unitario

HORA_DO_CORTE = 20
DELTA = 10.0

# Unidade explícita: `pd.Timedelta("24h")` dispara DeprecationWarning de unidade
# genérica no par pinado numpy 2.5.3 / pandas 2.3.3.
VINTE_E_QUATRO_HORAS = np.timedelta64(24, "h")


def _construir(df: pd.DataFrame) -> pd.DataFrame:
    return sn.features.construir(sn.preprocessamento.limpar(df))


def _antes_e_depois(coluna: str):
    """Features do lote base e do lote com **só o futuro** perturbado, para M01."""
    base = fabrica.lote(n_maquinas=3, n_horas=48, seed=42)
    perturbado = fabrica.perturbar_apenas_o_futuro(
        base, "M01", HORA_DO_CORTE, coluna, DELTA
    )
    return _construir(base), _construir(perturbado)


# --- contratos de forma ----------------------------------------------------

def test_construir_devolve_as_treze_colunas_na_ordem_canonica():
    X = _construir(fabrica.lote(seed=1))
    assert tuple(X.columns) == ORDEM_FEATURES


def test_construir_preserva_a_quantidade_de_linhas():
    limpo = sn.preprocessamento.limpar(fabrica.lote(seed=1))
    assert len(sn.features.construir(limpo)) == len(limpo)


def test_construir_nao_produz_nan():
    X = _construir(fabrica.com_dropout_de_vibracao(fabrica.lote(seed=1), 0.15, seed=2))
    assert X.notna().all().all()


def test_construir_preserva_a_ordem_de_entrada_sob_embaralhamento():
    """O quadro pode chegar em qualquer ordem; a saída acompanha a entrada, linha a linha."""
    limpo = sn.preprocessamento.limpar(fabrica.lote(n_maquinas=3, n_horas=36, seed=5))
    embaralhado = limpo.sample(frac=1.0, random_state=7)

    na_ordem = sn.features.construir(limpo)
    fora_de_ordem = sn.features.construir(embaralhado)

    pd.testing.assert_frame_equal(
        fora_de_ordem.loc[na_ordem.index], na_ordem, check_like=False
    )


def test_janelas_moveis_nao_atravessam_motores():
    """A janela de M02 não pode enxergar leitura de M01.

    Prova por construção: se as janelas vazassem entre motores, alterar todo o M01
    mudaria as features do M02.
    """
    base = fabrica.lote(n_maquinas=2, n_horas=48, seed=11)
    mexido = base.copy()
    de_m01 = mexido["id_maquina"] == "M01"
    mexido.loc[de_m01, "temperatura_c"] = mexido.loc[de_m01, "temperatura_c"] + 25.0

    antes, depois = _construir(base), _construir(mexido)
    linhas_m02 = base.index[base["id_maquina"] == "M02"]

    pd.testing.assert_frame_equal(antes.loc[linhas_m02], depois.loc[linhas_m02])


def test_operador_senior_marca_somente_op_07():
    lote = fabrica.lote(n_maquinas=3, n_horas=48, seed=13)
    limpo = sn.preprocessamento.limpar(lote)
    X = sn.features.construir(limpo)

    esperado = (limpo["id_operador"] == sn.features.OPERADOR_SENIOR).astype(float)
    np.testing.assert_array_equal(X["operador_senior"].to_numpy(), esperado.to_numpy())


def test_construir_exige_as_colunas_obrigatorias_com_value_error():
    limpo = sn.preprocessamento.limpar(fabrica.lote(seed=1))
    with pytest.raises(ValueError, match="colunas ausentes"):
        sn.features.construir(limpo.drop(columns=["vibracao_rms"]))


# --- os dois controles positivos -------------------------------------------

def test_temp_max_24h_nao_muda_quando_so_o_futuro_muda():
    """CONTROLE POSITIVO. `rolling(24)` sem `center` só olha para trás — tem de passar."""
    antes, depois = _antes_e_depois("temperatura_c")
    assert antes["temp_max_24h"].iloc[HORA_DO_CORTE] == pytest.approx(
        depois["temp_max_24h"].iloc[HORA_DO_CORTE]
    )


def test_vib_media_6h_nao_muda_quando_so_o_futuro_muda():
    """CONTROLE POSITIVO. Mesma janela de 6 h, mas sem `center` — tem de passar."""
    antes, depois = _antes_e_depois("vibracao_rms")
    assert antes["vib_media_6h"].iloc[HORA_DO_CORTE] == pytest.approx(
        depois["vib_media_6h"].iloc[HORA_DO_CORTE]
    )


# --- o teste-estrela do vazamento temporal ---------------------------------

@pytest.mark.defeito
@pytest.mark.xfail(strict=True, reason="D01 — `rolling(6, center=True)` faz a janela ser [t-2, t+3]: a feature de agora usa leitura que a planta só terá em 3 h")
def test_temp_media_6h_nao_muda_quando_so_o_futuro_muda():
    """A feature de `t` não pode usar leitura que a planta só terá em 3 horas.

    `rolling(6, center=True)` faz a janela ser `[t−2, t+3]`. O desempenho medido no
    conjunto de teste é, por construção, inalcançável em produção: na hora `t` o
    historiador simplesmente não tem `t+1`, `t+2`, `t+3`.
    """
    antes, depois = _antes_e_depois("temperatura_c")

    delta = (depois["temp_media_6h"] - antes["temp_media_6h"]).abs()
    afetadas = int((delta > 1e-9).sum())
    delta_em_t = float(delta.iloc[HORA_DO_CORTE])

    assert delta_em_t == pytest.approx(0.0, abs=1e-9), (
        f"temp_media_6h[t={HORA_DO_CORTE}] mudou {delta_em_t:.4f} °C ao perturbar "
        f"APENAS t+1..t+{len(antes) - HORA_DO_CORTE - 1} em +{DELTA} °C; "
        f"{afetadas} linhas do lote mudaram no total"
    )


# --- os demais defeitos da construção de features --------------------------

@pytest.mark.defeito
@pytest.mark.xfail(strict=True, reason="D08 — `shift(24)` conta linhas, não horas: após um furo no historiador é outra grandeza")
def test_delta_temp_24h_compara_com_a_leitura_de_vinte_e_quatro_horas_antes():
    """`shift(24)` conta **linhas**, não horas. Com furo no historiador, muda a grandeza."""
    base = fabrica.lote(n_maquinas=1, n_horas=72, seed=17)
    com_furo = fabrica.com_furo_no_historiador(base, "M01", a_partir_da_hora=30, horas=5)

    limpo = sn.preprocessamento.limpar(com_furo)
    X = sn.features.construir(limpo)

    posicao = 40
    instante = limpo["timestamp"].iloc[posicao]
    alvo = instante - VINTE_E_QUATRO_HORAS
    casadas = limpo.index[limpo["timestamp"] == alvo]
    assert len(casadas) == 1, "o instante de referência sumiu do lote"

    esperado = float(
        limpo["temperatura_c"].iloc[posicao] - limpo["temperatura_c"].loc[casadas[0]]
    )
    obtido = float(X["delta_temp_24h"].iloc[posicao])

    assert obtido == pytest.approx(esperado, abs=1e-9), (
        f"delta_temp_24h em {instante} devolveu {obtido:.4f} °C, mas a diferença real "
        f"contra {alvo} é {esperado:.4f} °C: com 5 h de furo, `shift(24)` foi buscar "
        "a leitura de 29 h antes"
    )


@pytest.mark.defeito
@pytest.mark.xfail(strict=True, reason="D09 — `center=True`, `min_periods=1` e `maquina_risco` por lote: reprocessar dá outra resposta")
def test_construir_e_estavel_entre_o_lote_inteiro_e_um_recorte():
    """Reprocessar um pedaço tem de dar a mesma resposta para as linhas em comum.

    O recorte é **temporal**, não por motor: recortar por motor não expõe nada, porque
    as janelas já são por motor e `maquina_risco` é calculada dentro do próprio motor.
    O reprocessamento real da planta é por janela de tempo — "rode as últimas 24 h de
    novo" — e é aí que a resposta muda.
    """
    base = fabrica.lote(n_maquinas=3, n_horas=48, seed=19)
    limpo = sn.preprocessamento.limpar(base)

    inteiro = sn.features.construir(limpo)

    corte = limpo["timestamp"].min() + VINTE_E_QUATRO_HORAS
    recorte_linhas = limpo.index[limpo["timestamp"] >= corte]
    recorte = sn.features.construir(limpo.loc[recorte_linhas])

    diferencas = (inteiro.loc[recorte_linhas] - recorte).abs().max()
    divergentes = {c: round(float(v), 4) for c, v in diferencas.items() if v > 1e-9}

    assert not divergentes, (
        f"reprocessar as últimas 24 h muda {len(divergentes)} das 13 features das "
        f"mesmas linhas: {divergentes}"
    )


@pytest.mark.defeito
@pytest.mark.xfail(strict=True, reason="D10 — `saida.loc[df.index, …]` com rótulos repetidos multiplica as linhas")
def test_construir_aceita_indice_duplicado_sem_multiplicar_linhas():
    """`pd.concat` de dois lotes é fluxo natural de reprocessamento."""
    a = sn.preprocessamento.limpar(fabrica.lote(n_maquinas=1, n_horas=24, seed=23))
    b = sn.preprocessamento.limpar(
        fabrica.lote(n_maquinas=1, n_horas=24, seed=29, inicio="2026-02-01 00:00:00")
    )
    juntos = pd.concat([a, b])  # sem reset_index: o índice se repete

    X = sn.features.construir(juntos)
    assert len(X) == len(juntos), (
        f"`saida.loc[df.index]` com rótulos repetidos explodiu o quadro: "
        f"{len(juntos)} linhas de entrada viraram {len(X)}"
    )


@pytest.mark.defeito
@pytest.mark.xfail(strict=True, reason="D15 — a checagem de colunas cobre 4 das 11 que `construir` consome; o resto vira KeyError")
@pytest.mark.parametrize("coluna", ["pressao", "rpm"])
def test_construir_nomeia_a_coluna_faltante_tambem_para_pressao_e_rpm(coluna):
    """A checagem de colunas cobre 4 das 11 que `construir` consome; o resto vira KeyError."""
    limpo = sn.preprocessamento.limpar(fabrica.lote(seed=31))
    with pytest.raises(ValueError, match=coluna):
        sn.features.construir(limpo.drop(columns=[coluna]))


@pytest.mark.defeito
@pytest.mark.xfail(strict=True, reason="D20 — `min_periods=1` ignora o NaN e transforma buraco de sensor em número confiante")
def test_temperatura_ausente_nao_e_silenciosamente_imputada():
    """`min_periods=1` transforma buraco de sensor em número confiante."""
    base = fabrica.lote(n_maquinas=1, n_horas=48, seed=37)
    limpo = sn.preprocessamento.limpar(base)
    limpo.loc[limpo.index[10:14], "temperatura_c"] = np.nan

    X = sn.features.construir(limpo)
    afetadas = X["temp_media_6h"].iloc[10:14]

    assert afetadas.isna().all(), (
        "temperatura ausente virou média finita "
        f"{[round(v, 3) for v in afetadas.tolist()]}: o buraco do sensor foi imputado "
        "sem que ninguém pedisse"
    )
