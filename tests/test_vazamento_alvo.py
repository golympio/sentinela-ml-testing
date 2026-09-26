"""O vazamento de alvo (D02) — o defeito que derruba a promoção da v2.

`features._risco_por_maquina` recalcula `maquina_risco` a partir de `falha_72h` sempre que a
coluna está presente. Como o alvo vem no CSV dos três conjuntos (SPEC P8), toda métrica
publicada sobre o Sentinela foi medida com o gabarito dentro da entrada.

Não é cenário hipotético: `scripts/treinar.py` chama `features.construir(limpo)` com o rótulo
ainda no quadro — e a linha anterior, `features._RISCO_CONGELADO = None  # força releitura`,
existe só para usar a tabela congelada que o passo seguinte torna inalcançável. O treino
passou pelo caminho vazado. Ver `docs/decisoes.md`.

Os números aqui saem de `evidencias/linha-de-base.md`.
"""
from __future__ import annotations

import json
import pathlib

import numpy as np
import pytest

import sentinela as sn
from suite import harness, metricas

pytestmark = pytest.mark.estatistico

CAMINHO_RISCO = pathlib.Path("/opt/sentinela/artefatos/risco_maquina.json")


@pytest.fixture(scope="module")
def tabela_congelada() -> dict:
    with CAMINHO_RISCO.open(encoding="utf-8") as arquivo:
        return json.load(arquivo)


@pytest.mark.defeito
@pytest.mark.xfail(strict=True, reason="D02 — `maquina_risco` é recalculada do rótulo: remover `falha_72h` muda a probabilidade")
def test_probabilidade_do_pipeline_nao_muda_se_o_rotulo_for_removido(lote_teste):
    """O teste que derruba a promoção da v2.

    Remover uma coluna que o serving não terá não pode mudar a probabilidade. Se muda, a
    métrica publicada mediu outra coisa que não o desempenho em produção.
    """
    _, com, _ = harness.prever_com_vazamento(lote_teste, "v2")
    _, sem, _ = harness.prever_sem_vazamento(lote_teste, "v2")

    diferentes = int((com != sem).sum())
    assert diferentes == 0, (
        f"{diferentes} de {len(com)} probabilidades mudam ao remover a coluna `falha_72h`; "
        f"|Δ| máximo = {np.abs(com - sem).max():.4f}"
    )


@pytest.mark.defeito
@pytest.mark.xfail(strict=True, reason="D02 — a feature é a média de `falha_72h` do grupo quando a coluna está presente")
def test_maquina_risco_nao_depende_do_rotulo_do_proprio_lote(lote_teste):
    """A feature tem de ser a mesma com e sem o rótulo no quadro."""
    com = harness.maquina_risco(lote_teste, vazar=True)
    sem = harness.maquina_risco(lote_teste, vazar=False)

    assert np.array_equal(com, sem), (
        f"`maquina_risco` difere em {int((com != sem).sum())} de {len(com)} linhas; "
        f"|Δ| máximo = {np.abs(com - sem).max():.6f}"
    )


@pytest.mark.defeito
@pytest.mark.xfail(strict=True, reason="D02 — o valor recalculado (máx. 0,428571) escapa do teto da tabela congelada (0,214286)")
def test_maquina_risco_fica_na_faixa_da_tabela_congelada(lote_teste, tabela_congelada):
    """O valor recalculado escapa da faixa que o modelo viu no treino.

    A tabela congelada é o que a planta teria em mãos. Um valor fora dela é uma feature que o
    modelo nunca encontrou durante o treino — extrapolação silenciosa no ponto de serving.
    """
    valores = np.array(list(tabela_congelada.values()), dtype=float)
    teto = float(valores.max())
    com = harness.maquina_risco(lote_teste, vazar=True)

    excedem = int((com > teto + 1e-9).sum())
    assert excedem == 0, (
        f"{excedem} de {len(com)} linhas têm `maquina_risco` acima do teto da tabela congelada "
        f"({teto:.6f}); máximo observado = {com.max():.6f}"
    )


@pytest.mark.defeito
@pytest.mark.xfail(strict=True, reason="D02 — rever o gabarito do lote muda a predição de leituras que não mudaram")
@pytest.mark.parametrize("versao", ["v1", "v2"])
def test_revisar_o_rotulo_do_lote_nao_muda_a_predicao(lote_teste, versao):
    """Rever o gabarito de um lote não pode mexer na predição das mesmas leituras.

    O cenário é o do próprio SUT: o README descreve `producao` como o lote "rotulado **depois**
    pela equipe". Rever rótulos é operação normal — e o modelo, que já rodou, não pode mudar de
    opinião sobre leituras que não mudaram.

    Aqui 21 das 168 leituras de M02 passam a constar como falha. **Nenhum sensor é tocado.**

    Dois cuidados que este teste aprendeu na marra, ambos registrados em `docs/mapa-defeitos.md`:

    - **Assertar probabilidade, não decisão.** Com 2 rótulos revistos as probabilidades já se
      movem; a primeira decisão só vira com 21. Um oráculo de decisão binária dá o defeito por
      inexistente numa faixa larga.
    - **Renomear o motor não serve de experimento.** `maquina_risco` é a média **do grupo**;
      renomear o grupo inteiro preserva a média, e partir o grupo mexe nas janelas móveis — o que
      mediria D09, não D02. Mexer só na coluna de rótulo isola o mecanismo.
    """
    revisado = lote_teste.copy()
    do_motor = revisado.index[revisado["id_maquina"] == "M02"]
    revisado.loc[do_motor[:21], "falha_72h"] = 1

    intocadas = ["timestamp", "id_maquina", "temperatura_c", "vibracao_rms", "pressao",
                 "corrente_a", "rpm", "horas_operacao", "id_operador", "turno"]
    assert revisado[intocadas].equals(lote_teste[intocadas])

    _, antes, _ = harness.prever_com_vazamento(lote_teste, versao)
    _, depois, _ = harness.prever_com_vazamento(revisado, versao)

    mudaram = int((antes != depois).sum())
    assert mudaram == 0, (
        f"{versao}: rever 21 de 168 rótulos de M02, sem tocar em nenhum sensor, mudou "
        f"{mudaram} de {len(antes)} probabilidades; |Δ| máximo = "
        f"{np.abs(antes - depois).max():.6f}"
    )


@pytest.mark.defeito
@pytest.mark.xfail(strict=True, reason="D02 — o vazamento infla recall, F2 e PR-AUC; no teste a PR-AUC da v1 sobe 28,68 pp")
@pytest.mark.parametrize("versao", ["v1", "v2"])
def test_metricas_com_e_sem_vazamento_sao_iguais(lote_teste, versao):
    """Δrecall, ΔF2 e ΔPR-AUC têm de ser zero. O que sobra é a inflação."""
    y, proba_com, pred_com = harness.prever_com_vazamento(lote_teste, versao)
    _, proba_sem, pred_sem = harness.prever_sem_vazamento(lote_teste, versao)

    d_recall = sn.avaliacao.metricas(y, pred_com)["recall"] - sn.avaliacao.metricas(y, pred_sem)["recall"]
    d_f2 = metricas.fbeta(y, pred_com, 2.0) - metricas.fbeta(y, pred_sem, 2.0)
    d_prauc = metricas.average_precision(y, proba_com) - metricas.average_precision(y, proba_sem)

    assert (abs(d_recall), abs(d_f2), abs(d_prauc)) == pytest.approx((0.0, 0.0, 0.0), abs=1e-9), (
        f"{versao}: o vazamento infla Δrecall={100*d_recall:+.2f} pp, ΔF2={100*d_f2:+.2f} pp, "
        f"ΔPR-AUC={100*d_prauc:+.2f} pp"
    )


def test_tabela_congelada_cobre_os_vinte_e_cinco_motores(tabela_congelada):
    """Verde: a tabela cobre M01..M25 e o *fallback* de média é calculável."""
    esperados = {f"M{n:02d}" for n in range(1, 26)}
    assert set(tabela_congelada) == esperados

    valores = list(tabela_congelada.values())
    assert all(0.0 <= v <= 1.0 for v in valores)
    media = sum(valores) / len(valores)
    assert 0.0 < media < 1.0, f"fallback de média degenerado: {media}"
