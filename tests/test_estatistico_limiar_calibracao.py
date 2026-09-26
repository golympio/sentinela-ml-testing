"""Limiar de decisão e calibração das probabilidades (Bloco B).

Duas perguntas que a acurácia não responde:

1. **O 0,5 é o limiar certo?** `modelo.LIMIAR_PADRAO` vale 0,5 porque é o default de todo
   mundo, não porque alguém mediu o custo da planta. Um falso negativo é um motor queimado;
   um falso positivo é uma equipe deslocada à toa. A assimetria vira número aqui.
2. **A probabilidade quer dizer o que diz?** Se o painel anuncia 85 % e falham 35 %,
   priorizar por risco é priorizar por ruído.

Tudo medido no conjunto **teste**, modo **sem vazamento** — a consequência travada no
HANDOFF 03 (`docs/decisoes.md`): é esse o número que a planta obtém, e nenhuma leitura desta
fase pode se apoiar em acurácia nem no modo com vazamento.
"""
from __future__ import annotations

import numpy as np
import pytest

import sentinela as sn
from suite import calibracao, harness, metricas

pytestmark = pytest.mark.estatistico

VERSOES = ("v1", "v2")
CONJUNTO = "teste"

# Varredura de 0,05 a 0,95 em passos de 0,05: 19 pontos, acima do piso de 10 de V15.
LIMIARES = tuple(round(float(t), 2) for t in np.arange(0.05, 0.9501, 0.05))

# Custo relativo da planta: deixar de prever uma falha custa 20× abrir uma ordem à toa.
# A razão está justificada em `docs/decisoes.md`; o que importa ao teste é que ela é
# **assimétrica** e explícita, em vez de escondida no 0,5.
CUSTO_FN = 20
CUSTO_FP = 1


@pytest.fixture(scope="session")
def medidas():
    """`(y, proba)` por versão, no conjunto de teste, sem vazamento. Uma passagem só."""
    lote = sn.dados.carregar(CONJUNTO)
    saida = {}
    for versao in VERSOES:
        y, proba, _ = harness.prever_sem_vazamento(lote, versao)
        saida[versao] = (y, proba)
    return saida


def _custo(y, proba, limiar: float) -> int:
    pred = (proba >= limiar).astype(int)
    fp = int(((pred == 1) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())
    return CUSTO_FN * fn + CUSTO_FP * fp


def _varredura(y, proba) -> list[dict]:
    tabela = []
    for limiar in LIMIARES:
        pred = (proba >= limiar).astype(int)
        base = sn.avaliacao.metricas(y, pred)
        tabela.append(
            {
                "limiar": limiar,
                "precisao": round(float(base["precisao"]), 6),
                "recall": round(float(base["recall"]), 6),
                "f2": round(metricas.fbeta(y, pred, beta=2.0), 6),
                "custo": _custo(y, proba, limiar),
            }
        )
    return tabela


def test_varredura_de_limiar_cobre_precisao_e_recall(medidas, medicoes):
    """A tabela que o relatório cita, e o insumo de V15.

    Verde por construção: aqui não há veredito, há medição. O que se asserta é que a
    varredura de fato percorre o espaço de decisão — se precisão e recall não se movem, o
    limiar não é a alavanca que supomos e todo o resto desta fase é sobre outra coisa.
    """
    registros = []
    for versao in VERSOES:
        y, proba = medidas[versao]
        tabela = _varredura(y, proba)
        registros.extend({"versao": versao, **linha} for linha in tabela)

        recalls = [linha["recall"] for linha in tabela]
        precisoes = [linha["precisao"] for linha in tabela]
        assert recalls == sorted(recalls, reverse=True), (
            f"{versao}: subir o limiar deveria só reduzir o recall"
        )
        assert max(recalls) - min(recalls) > 0.3, f"{versao}: a varredura mal move o recall"
        assert max(precisoes) - min(precisoes) > 0.2, f"{versao}: a varredura mal move a precisão"

    assert len(registros) == 2 * len(LIMIARES) == 38
    medicoes["limiar"] = registros


def test_recall_com_precisao_minima_existe_para_a_v1(medidas):
    """"Quantas falhas eu pego se aceito que no máximo metade das ordens seja em vão?"

    É a pergunta que a manutenção faz de verdade, e ela tem resposta: existe corte com
    precisão ≥ 0,5 e recall bem acima de zero.
    """
    y, proba = medidas["v1"]
    recall, limiar = metricas.recall_com_precisao_minima(y, proba, 0.5)

    assert recall > 0.0, "nenhum corte atinge precisão 0,5 com recall não nulo"
    assert np.isfinite(limiar)
    assert recall == pytest.approx(0.6687, abs=1e-3), f"recall@precisão≥0,5 medido: {recall:.4f}"


@pytest.mark.defeito
@pytest.mark.xfail(
    strict=True,
    reason="D11 — o 0,5 do sistema não maximiza F2: v2 tem ótimo em 0,20 (+0,0865 de F2)",
)
@pytest.mark.parametrize("versao", VERSOES)
def test_limiar_0_5_maximiza_f2(medidas, versao):
    """O 0,5 do sistema deveria ser o melhor limiar para F2 (recall pesando 4×)."""
    y, proba = medidas[versao]
    tabela = _varredura(y, proba)
    melhor = max(tabela, key=lambda linha: linha["f2"])
    em_meio = next(linha for linha in tabela if linha["limiar"] == 0.5)

    assert melhor["limiar"] == 0.5, (
        f"{versao}: F2 é máximo em {melhor['limiar']:.2f} (F2={melhor['f2']:.4f}), "
        f"não em 0,50 (F2={em_meio['f2']:.4f}); diferença de {melhor['f2'] - em_meio['f2']:+.4f}"
    )


@pytest.mark.parametrize(
    "versao",
    [
        # A v1 PASSA: com FN valendo 20× FP, o custo dela é mínimo exatamente em 0,50.
        # Medido, não suposto — o HANDOFF previa o contrário. Marcar a função inteira
        # daria XPASS aqui e derrubaria a suíte (padrão de D17, `docs/decisoes.md`).
        "v1",
        pytest.param(
            "v2",
            marks=[
                pytest.mark.defeito,
                pytest.mark.xfail(
                    strict=True,
                    reason="D11 — herdar o limiar 0,5 da v1 custa 2.605 a mais na v2 (4.393 contra 1.788)",
                ),
            ],
        ),
    ],
)
def test_limiar_de_custo_minimo_e_0_5(medidas, versao):
    """Com FN valendo 20× FP, o limiar de custo mínimo deveria ser o do sistema."""
    y, proba = medidas[versao]
    custos = {limiar: _custo(y, proba, limiar) for limiar in LIMIARES}
    melhor = min(custos, key=custos.get)

    assert melhor == 0.5, (
        f"{versao}: custo mínimo em {melhor:.2f} (custo={custos[melhor]}), "
        f"não em 0,50 (custo={custos[0.5]}); "
        f"o limiar do sistema custa {custos[0.5] - custos[melhor]} a mais"
    )


def test_brier_da_v1_e_da_v2(medidas, medicoes):
    """Registra o Brier por versão. Verde: é medição, não veredito."""
    brier = {}
    for versao in VERSOES:
        y, proba = medidas[versao]
        brier[versao] = round(calibracao.brier(y, proba), 6)
        assert 0.0 <= brier[versao] <= 1.0

    # a v2 tem Brier melhor — e ainda assim erra mais falhas; é o ponto do relatório
    assert brier["v2"] < brier["v1"]
    medicoes.setdefault("calibracao", {})["brier"] = brier


@pytest.mark.defeito
@pytest.mark.xfail(
    strict=True,
    reason="D12 — ECE de 19,06 p.p. (v1) e 5,76 p.p. (v2) contra o teto de 5 p.p.",
)
@pytest.mark.parametrize("versao", VERSOES)
def test_ece_por_versao_fica_abaixo_de_cinco_pontos(medidas, versao):
    """ECE ≤ 5 p.p.: a confiança anunciada não deveria distar mais que isso do observado."""
    y, proba = medidas[versao]
    medido = calibracao.ece(y, proba)

    assert medido <= 0.05, f"{versao}: ECE = {medido:.4f} ({100 * medido:.2f} p.p.)"


@pytest.mark.defeito
@pytest.mark.xfail(
    strict=True,
    reason="D12 — a frequência observada cai ao subir de faixa: 3 quebras na v1, 1 na v2",
)
@pytest.mark.parametrize("versao", VERSOES)
def test_curva_de_confiabilidade_e_monotona(medidas, versao):
    """Faixa de probabilidade maior ⇒ frequência de falha observada maior.

    É o mínimo que se pede de um score usado para **ordenar** motores: se a ordem se quebra,
    priorizar pelo número é pior que priorizar pelo palpite de quem conhece a planta.
    """
    y, proba = medidas[versao]
    tabela = calibracao.bins_de_confiabilidade(y, proba)
    observado = [faixa["observado"] for faixa in tabela]

    quebras = [
        (tabela[i]["faixa"], observado[i - 1], observado[i])
        for i in range(1, len(observado))
        if observado[i] < observado[i - 1]
    ]
    assert not quebras, f"{versao}: {len(quebras)} quebra(s) de monotonia: " + "; ".join(
        f"faixa {lo:.1f}–{hi:.1f} caiu de {antes:.4f} para {depois:.4f}"
        for (lo, hi), antes, depois in quebras
    )


@pytest.mark.defeito
@pytest.mark.xfail(
    strict=True,
    reason="D12 — superconfiança nas 20 faixas: gap máximo 0,4227 (v1) e 0,3140 (v2)",
)
@pytest.mark.parametrize("versao", VERSOES)
def test_probabilidade_media_prevista_bate_com_a_frequencia_observada_por_faixa(
    medidas, versao, medicoes
):
    """O pedido literal do guia do aluno, faixa a faixa.

    Tolerância de 10 p.p.: é generosa de propósito, para que uma falha aqui seja
    indiscutível e não uma discussão sobre onde se põe a régua.
    """
    y, proba = medidas[versao]
    tabela = calibracao.bins_de_confiabilidade(y, proba)
    medicoes.setdefault("calibracao", {}).setdefault("bins", {})[versao] = tabela

    piores = sorted(tabela, key=lambda faixa: abs(faixa["gap"]), reverse=True)[:3]
    maior = abs(piores[0]["gap"])

    assert maior <= 0.10, f"{versao}: maior desvio |confiança − observado| = {maior:.4f}; piores faixas: " + "; ".join(
        f"{faixa['faixa'][0]:.1f}–{faixa['faixa'][1]:.1f} prometeu {faixa['confianca']:.4f} "
        f"e observou {faixa['observado']:.4f} (n={faixa['n']})"
        for faixa in piores
    )
