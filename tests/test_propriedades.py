"""Testes baseados em propriedade (aula 2), sobre lotes da fábrica.

Um teste de exemplo prova que o código funciona *naquele* caso. Uma propriedade diz o
que tem de valer para **todo** lote válido, e deixa o `hypothesis` procurar o
contraexemplo. As seis propriedades aqui são invariantes que não dependem de versão de
biblioteca nem de offset de janela.

`max_examples=50` e `deadline=None`: o custo é rodar o pipeline dezenas de vezes, e o
relógio de parede varia demais entre máquinas para virar critério de falha.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

import sentinela as sn
from sentinela.features import ORDEM_FEATURES
from suite import fabrica

pytestmark = [pytest.mark.unitario, pytest.mark.propriedade]

CONFIG = settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)

# Lotes pequenos e válidos: o que varia é a semente, o nº de motores e o de horas.
LOTES = st.builds(
    fabrica.lote,
    n_maquinas=st.integers(min_value=1, max_value=4),
    n_horas=st.integers(min_value=8, max_value=60),
    seed=st.integers(min_value=0, max_value=10_000),
)


@CONFIG
@given(lote=LOTES)
def test_limpar_e_idempotente_para_qualquer_lote(lote):
    uma = sn.preprocessamento.limpar(lote)
    duas = sn.preprocessamento.limpar(uma)
    pd.testing.assert_frame_equal(uma, duas)


@CONFIG
@given(lote=LOTES, semente=st.integers(min_value=0, max_value=10_000))
def test_construir_preserva_a_ordem_para_qualquer_permutacao(lote, semente):
    limpo = sn.preprocessamento.limpar(lote)
    embaralhado = limpo.sample(frac=1.0, random_state=semente)

    na_ordem = sn.features.construir(limpo)
    fora_de_ordem = sn.features.construir(embaralhado)

    pd.testing.assert_frame_equal(fora_de_ordem.loc[na_ordem.index], na_ordem)


@CONFIG
@given(lote=LOTES)
def test_features_ficam_finitas_para_qualquer_lote_valido(lote):
    X = sn.features.construir(sn.preprocessamento.limpar(lote))
    assert np.isfinite(X.to_numpy(dtype=float)).all()
    assert tuple(X.columns) == ORDEM_FEATURES


@CONFIG
@given(lote=LOTES)
def test_temp_media_6h_esta_entre_o_minimo_e_o_maximo_da_janela(lote):
    """Média de qualquer subconjunto cai entre o mínimo e o máximo do motor.

    Propriedade verdadeira para **qualquer** janela — centrada ou não —, de propósito:
    é o que a torna imune ao offset de janela par do pandas. Quem acusa a janela
    centrada é `test_temp_media_6h_nao_muda_quando_so_o_futuro_muda` (D01).
    """
    limpo = sn.preprocessamento.limpar(lote)
    X = sn.features.construir(limpo)

    for maquina, grupo in limpo.groupby("id_maquina", sort=False):
        media = X.loc[grupo.index, "temp_media_6h"]
        assert media.min() >= grupo["temperatura_c"].min() - 1e-9, maquina
        assert media.max() <= grupo["temperatura_c"].max() + 1e-9, maquina


@CONFIG
@given(lote=LOTES, versao=st.sampled_from(sn.modelo.VERSOES))
def test_probabilidade_esta_sempre_em_zero_um(lote, versao):
    saida = sn.pipeline.executar(lote, versao=versao)
    assert saida["probabilidade"].between(0.0, 1.0).all()


@CONFIG
@given(
    lote=LOTES,
    limiares=st.tuples(
        st.floats(min_value=0.05, max_value=0.94),
        st.floats(min_value=0.05, max_value=0.94),
    ),
)
def test_decisao_e_monotona_no_limiar(lote, limiares):
    """Limiar maior ⇒ o conjunto de decisões 1 só pode encolher."""
    baixo, alto = sorted(limiares)
    X = sn.features.construir(sn.preprocessamento.limpar(lote))
    modelo = sn.modelo.carregar("v1")

    com_baixo = set(np.flatnonzero(modelo.prever(X, limiar=baixo)))
    com_alto = set(np.flatnonzero(modelo.prever(X, limiar=alto)))

    assert com_alto <= com_baixo, (
        f"limiar {alto:.3f} decidiu 1 em linhas que o limiar {baixo:.3f} não decidiu: "
        f"{sorted(com_alto - com_baixo)[:5]}"
    )
