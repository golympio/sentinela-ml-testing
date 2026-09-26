"""Drift entre o conjunto de teste e produção (Bloco B).

O Sentinela foi avaliado no conjunto de teste e roda sobre `producao`. Nada no sistema
compara os dois. Aqui a comparação existe — e o resultado interessante não é "há drift", é
**qual detector vê o quê**: a diferença de médias fica calada em todas as seis colunas de
sensor, enquanto KS acusa em cinco e o PSI põe duas em faixa de atenção.

`teste` é o **baseline** e `producao` é o que se compara contra ele, em todos os testes deste
arquivo — inclusive nos de estabilidade, que comparam o mesmo par para não misturar duas
perguntas (ver `docs/decisoes.md`).

> **Contexto que muda a leitura** (`docs/decisoes.md`, Bloco A): `treino` e `producao` têm
> linhas fora da faixa da ficha técnica e o conjunto de **teste não tem nenhuma**. O baseline
> desta comparação é, portanto, o único conjunto limpo dos três — e ainda assim produção
> derivou dele.
"""
from __future__ import annotations

import pytest

import sentinela as sn
from suite import drift, ficha

pytestmark = pytest.mark.estatistico

ALPHA = 0.01
LIMIAR_MEDIA = 0.10
TOLERANCIA_ESTABILIDADE = 0.02      # 2 p.p., conforme SPEC §4.2


@pytest.fixture(scope="session")
def conjuntos():
    return {c: sn.dados.carregar(c) for c in ("treino", "teste", "producao")}


@pytest.fixture(scope="session")
def colunas_de_sensor(conjuntos):
    return [c for c in ficha.FICHA if c in conjuntos["teste"].columns]


def test_media_da_temperatura_nao_acusa_drift_entre_teste_e_producao(conjuntos):
    """A diferença de médias **passa** — e é esse o ponto.

    Documenta a cegueira do detector mais barato: a temperatura mudou de forma o bastante
    para o KS acusar com p = 3,5e-33, e a média mal se move (1,76 %).
    """
    medida = drift.detectar_drift_media(
        conjuntos["teste"]["temperatura_c"], conjuntos["producao"]["temperatura_c"], LIMIAR_MEDIA
    )

    assert not medida["drift"], f"a média acusou: {medida}"
    assert medida["delta_relativo"] < 0.05, (
        f"a média mudou {100 * medida['delta_relativo']:.2f} % — o teste deixou de ilustrar a cegueira"
    )


def test_ks_acusa_drift_na_temperatura(conjuntos):
    """KS olha a acumulada inteira e enxerga o que a média não enxerga."""
    medida = drift.detectar_drift_ks(
        conjuntos["teste"]["temperatura_c"], conjuntos["producao"]["temperatura_c"], ALPHA
    )

    assert medida["drift"], f"KS não acusou: p = {medida['ks_p']:.4g}"
    assert medida["ks_p"] < ALPHA
    # o tamanho do efeito, que o p não dá: sem isto, "p pequeno" viraria "efeito grande"
    assert medida["estatistica"] == pytest.approx(0.1338, abs=1e-3)


def test_psi_acusa_drift_na_temperatura(conjuntos):
    """PSI põe a temperatura em faixa de **atenção** — e é o único que fala em tamanho.

    "Escolher o detector é escolher o que se aceita não enxergar": a média diz que está tudo
    bem, o KS diz que mudou com p astronômico, e o PSI diz **quanto** mudou — 0,18, atenção,
    não drift severo. As três frases são sobre o mesmo dado.
    """
    valor = drift.psi(conjuntos["teste"]["temperatura_c"], conjuntos["producao"]["temperatura_c"])

    assert valor > drift.PSI_ESTAVEL, f"PSI = {valor:.4f} não passou de {drift.PSI_ESTAVEL}"
    assert drift.classificar_psi(valor) == "atencao"
    assert valor == pytest.approx(0.1798, abs=1e-3)


@pytest.mark.defeito
@pytest.mark.xfail(
    strict=True,
    reason="D13 — 5 das 6 colunas de sensor mudaram de distribuição e a média não acusa nenhuma",
)
def test_distribuicoes_de_entrada_sao_as_mesmas_entre_teste_e_producao(
    conjuntos, colunas_de_sensor, medicoes
):
    """Nenhuma coluna de sensor deveria acusar drift entre o baseline e produção."""
    medido = {
        coluna: drift.medir(conjuntos["teste"][coluna], conjuntos["producao"][coluna], LIMIAR_MEDIA, ALPHA)
        for coluna in colunas_de_sensor
    }
    medicoes["drift"] = medido

    acusadas = {
        coluna: m for coluna, m in medido.items() if m["ks_acusa"] or m["psi_classe"] != "estavel"
    }
    assert not acusadas, (
        f"{len(acusadas)} de {len(medido)} colunas acusam drift: "
        + "; ".join(
            f"{coluna} (KS p={m['ks_p']:.3g}, PSI={m['psi']:.4f} → {m['psi_classe']}, "
            f"mas Δmédia de só {100 * m['delta_relativo']:.2f} %)"
            for coluna, m in acusadas.items()
        )
    )


def test_taxa_de_dropout_de_vibracao_e_estavel_entre_conjuntos(conjuntos, medicoes):
    """O dropout do sensor de vibração não deveria mudar entre baseline e produção.

    Comparação **teste × produção**, o mesmo par dos demais testes deste arquivo. A taxa do
    `treino` é registrada junto, mas não entra no assert: treino × teste é outra pergunta
    (descasamento treino/serviço), decidida e registrada em `docs/decisoes.md`.
    """
    taxas = {c: float(df["vibracao_rms"].isna().mean()) for c, df in conjuntos.items()}
    medicoes.setdefault("estabilidade", {})["dropout_vibracao"] = {
        c: round(v, 6) for c, v in taxas.items()
    }

    delta = abs(taxas["teste"] - taxas["producao"])
    assert delta <= TOLERANCIA_ESTABILIDADE, (
        f"dropout teste={taxas['teste']:.4f} producao={taxas['producao']:.4f} "
        f"({100 * delta:.2f} p.p.); treino={taxas['treino']:.4f}"
    )


def test_proporcao_de_psi_e_estavel_entre_conjuntos(conjuntos, medicoes):
    """A fração de CLPs reportando em psi não deveria mudar entre conjuntos.

    Importa por causa de D03: a pressão em psi nunca é convertida, então uma mudança nesta
    proporção mudaria a distribuição efetiva de `pressao` sem nenhum sensor ter mudado.
    """
    proporcoes = {
        c: float((df["unidade_pressao"].str.lower() == "psi").mean()) for c, df in conjuntos.items()
    }
    medicoes.setdefault("estabilidade", {})["proporcao_psi"] = {
        c: round(v, 6) for c, v in proporcoes.items()
    }

    delta = abs(proporcoes["teste"] - proporcoes["producao"])
    assert delta <= TOLERANCIA_ESTABILIDADE, (
        f"proporção em psi teste={proporcoes['teste']:.4f} producao={proporcoes['producao']:.4f} "
        f"({100 * delta:.2f} p.p.)"
    )


def test_prevalencia_do_alvo_e_estavel_entre_conjuntos(conjuntos, medicoes):
    """Drift de **rótulo** (label shift): a taxa de falha muda entre os conjuntos?

    É o drift que nenhum detector de entrada pega, porque não está na entrada. Se a
    prevalência muda, precisão e recall mudam sem o modelo ter mudado uma vírgula.
    """
    prevalencias = {c: float(df["falha_72h"].mean()) for c, df in conjuntos.items()}
    medicoes.setdefault("estabilidade", {})["prevalencia"] = {
        c: round(v, 6) for c, v in prevalencias.items()
    }

    delta = abs(prevalencias["teste"] - prevalencias["producao"])
    assert delta <= TOLERANCIA_ESTABILIDADE, (
        f"prevalência teste={prevalencias['teste']:.4f} producao={prevalencias['producao']:.4f} "
        f"({100 * delta:.2f} p.p.); treino={prevalencias['treino']:.4f}"
    )
