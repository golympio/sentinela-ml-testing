"""O pipeline ponta a ponta: leituras cruas → ordens de manutenção.

Dois testes só, de propósito (SPEC §4.2): o contrato de saída com o oráculo mínimo
"não é preditor constante", e o descarte silencioso de linhas — que aqui aparece no
lugar onde a planta o sentiria, o painel com menos motores do que o historiador mandou.
"""
from __future__ import annotations

import pytest

import sentinela as sn
from suite import fabrica

pytestmark = pytest.mark.unitario


def test_pipeline_devolve_decisao_binaria_para_cada_leitura():
    """Uma decisão por leitura limpa, com as quatro colunas do contrato.

    O último par de asserts é o oráculo mínimo da aula 6: um modelo que responde sempre
    a mesma coisa passaria em quase todo teste de forma, e não serve para nada.
    """
    lote = fabrica.lote(n_maquinas=5, n_horas=72, seed=42)
    limpo = sn.preprocessamento.limpar(lote)
    saida = sn.pipeline.executar(lote, versao="v1", limiar=0.5)

    assert len(saida) == len(limpo)
    assert {"id_maquina", "timestamp", "probabilidade", "predicao"} <= set(saida.columns)
    assert set(saida["predicao"].unique()) <= {0, 1}
    assert saida["probabilidade"].between(0.0, 1.0).all()

    # não é preditor constante
    assert saida["probabilidade"].nunique() > 1, "o modelo devolveu a mesma probabilidade para tudo"

    # o limiar tem efeito, e na direção certa
    severo = sn.pipeline.executar(lote, versao="v1", limiar=0.9)
    permissivo = sn.pipeline.executar(lote, versao="v1", limiar=0.1)
    assert severo["predicao"].sum() < permissivo["predicao"].sum()


@pytest.mark.defeito
@pytest.mark.xfail(
    strict=True,
    reason=(
        "D05 — `limpo[limpo['rpm'] >= 1.0]` descarta leituras sem registro: o painel "
        "mostra menos motores do que o historiador mandou, e ninguém é avisado"
    ),
)
def test_pipeline_nao_perde_linhas_silenciosamente():
    """Lote com rpm inválido: as leituras somem do painel sem deixar rastro."""
    lote = fabrica.lote(n_maquinas=3, n_horas=48, seed=42)
    com_invalidas = lote.copy()
    com_invalidas.loc[com_invalidas.index[:7], "rpm"] = 0.0

    saida = sn.pipeline.executar(com_invalidas)

    assert len(saida) == len(com_invalidas), (
        f"{len(com_invalidas) - len(saida)} leituras desapareceram entre a entrada e o "
        "painel, sem nenhum registro auditável do que saiu"
    )
