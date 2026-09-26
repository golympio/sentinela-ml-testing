"""O contrato de `Modelo` — o que ele aceita, o que ele rejeita e o que decide.

`_matriz` valida apenas forma e finitude (SPEC P5): aceita 500 °C e rpm negativo sem
piscar. Aqui o foco é o contrato de entrada e o caminho de serving de uma leitura só,
`prever_registro`, que é o do painel da sala de controle — e o mais frágil.
"""
from __future__ import annotations

import numpy as np
import pytest

import sentinela as sn
from sentinela.features import ORDEM_FEATURES
from suite import fabrica

pytestmark = pytest.mark.unitario


@pytest.fixture
def features():
    lote = fabrica.lote(n_maquinas=2, n_horas=36, seed=42)
    return sn.features.construir(sn.preprocessamento.limpar(lote))


@pytest.fixture
def modelo():
    return sn.modelo.carregar("v1")


def test_carregar_versao_desconhecida_levanta_value_error():
    with pytest.raises(ValueError, match="versão desconhecida"):
        sn.modelo.carregar("v3")


def test_matriz_rejeita_nan_e_infinito(modelo, features):
    com_nan = features.copy()
    com_nan.iloc[0, 0] = np.nan
    with pytest.raises(ValueError, match="NaN ou infinito"):
        modelo.prever_proba(com_nan)

    com_inf = features.copy()
    com_inf.iloc[0, 0] = np.inf
    with pytest.raises(ValueError, match="NaN ou infinito"):
        modelo.prever_proba(com_inf)


def test_matriz_rejeita_forma_errada(modelo):
    with pytest.raises(ValueError, match=r"esperado \(n, 13\)"):
        modelo.prever_proba(np.zeros((4, 5)))


def test_prever_proba_independe_da_ordem_das_colunas_do_dataframe(modelo, features):
    """`_matriz` reindexa pelo nome quando recebe DataFrame — esta é a garantia."""
    invertido = features[list(reversed(ORDEM_FEATURES))]
    np.testing.assert_array_equal(
        modelo.prever_proba(features), modelo.prever_proba(invertido)
    )


def test_prever_usa_limiar_maior_ou_igual(modelo, features):
    """Probabilidade exatamente igual ao limiar decide 1, não 0."""
    proba = modelo.prever_proba(features)
    limiar = float(proba[0])
    decisao = modelo.prever(features, limiar=limiar)
    assert decisao[0] == 1, (
        f"probabilidade {limiar} igual ao limiar {limiar} decidiu {decisao[0]}"
    )


@pytest.mark.defeito
@pytest.mark.xfail(strict=True, reason="D07 — `prever_registro` monta o vetor por `.values()` e ignora as chaves")
def test_prever_registro_respeita_as_chaves_do_dicionario(modelo, features):
    """O painel manda um dicionário. Se a ordem das chaves mudar, a decisão não pode mudar.

    `prever_registro` faz `[float(v) for v in registro.values()]` e **ignora as chaves**:
    um dicionário reordenado vira outro vetor de features, silenciosamente.

    O teste varre o lote inteiro em vez de olhar uma linha: numa linha só, as duas
    decisões coincidem por acaso quase metade das vezes e o defeito passa batido.
    """
    divergentes = []
    for i in range(len(features)):
        registro = features.iloc[i].to_dict()
        embaralhado = {k: registro[k] for k in reversed(list(registro))}
        if modelo.prever_registro(registro) != modelo.prever_registro(embaralhado):
            divergentes.append(i)

    assert not divergentes, (
        f"{len(divergentes)} de {len(features)} leituras "
        f"({len(divergentes) / len(features):.1%}) mudam de decisão só por reordenar "
        f"as chaves do dicionário; primeiras: {divergentes[:5]}"
    )


@pytest.mark.defeito
@pytest.mark.xfail(strict=True, reason="D07 — chave desconhecida entra como feature em vez de virar erro")
def test_prever_registro_rejeita_dicionario_com_chave_desconhecida(modelo, features):
    """Chave inventada tem de virar erro, não predição silenciosa."""
    registro = features.iloc[0].to_dict()
    registro.pop("turno")
    registro["temperatura_media_seis_horas"] = 70.0

    with pytest.raises(ValueError):
        modelo.prever_registro(registro)
