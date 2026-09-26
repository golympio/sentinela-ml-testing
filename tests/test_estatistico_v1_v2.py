"""A comparação v1 × v2, com incerteza (Bloco B).

A Nortemec quer promover a v2 por **+3,5 pp de acurácia** no conjunto de teste. Este
arquivo pega essa afirmação e a submete às perguntas que ela não respondeu: o ganho é de
acurácia sobre um alvo com prevalência de ~15 %, medido no único conjunto sem violação de
ficha técnica, e no modo em que o rótulo vaza para dentro da entrada.

**Convenção de sinal (SPEC §5, `docs/decisoes.md`).** Toda diferença pareada é
`métrica(v1) − métrica(v2)`: `lo > 0` ⇒ v1 melhor. Inverter os argumentos inverteria o
veredito sem quebrar teste nenhum — por isso a leitura passa por `estatistica.veredito()` e
nunca é reescrita aqui.

**Leitura sem vazamento**, exceto onde o teste existe justamente para reproduzir o número da
empresa (`test_v2_ganha_acuracia_sobre_v1`), que só existe no modo com vazamento e está
marcado como tal.
"""
from __future__ import annotations

import numpy as np
import pytest

import sentinela as sn
from suite import estatistica, harness, metricas

pytestmark = pytest.mark.estatistico

ALPHA = 0.01


@pytest.fixture(scope="session")
def comparacao():
    """`(y, proba, predicao)` de v1 e v2 lado a lado, por conjunto, sem vazamento."""
    saida = {}
    for conjunto in ("teste", "producao"):
        lote = sn.dados.carregar(conjunto)
        y1, proba1, pred1 = harness.prever_sem_vazamento(lote, "v1")
        y2, proba2, pred2 = harness.prever_sem_vazamento(lote, "v2")
        assert np.array_equal(y1, y2), "os dois modos têm de ver o mesmo y para parear"
        saida[conjunto] = {
            "y": y1,
            "v1": {"proba": proba1, "pred": pred1},
            "v2": {"proba": proba2, "pred": pred2},
        }
    return saida


def _recall(y, pred) -> float:
    return float(sn.avaliacao.metricas(y, pred)["recall"])


def test_acuracia_do_preditor_sempre_zero_e_a_linha_de_base_honesta(comparacao):
    """Prever "nunca falha" para tudo já acerta ~84 % — e não abre uma ordem sequer.

    É a régua que faltava na decisão da Nortemec: qualquer acurácia tem de ser lida contra
    este número, não contra zero.
    """
    y = comparacao["teste"]["y"]
    sempre_zero = np.zeros_like(y)
    acuracia = float(sn.avaliacao.metricas(y, sempre_zero)["acuracia"])

    assert acuracia == pytest.approx(0.8440, abs=1e-3)
    assert _recall(y, sempre_zero) == 0.0, "o preditor sempre-zero não pega falha nenhuma"

    # e a v1, o modelo que a planta usa, tem acurácia ABAIXO dessa régua
    acuracia_v1 = float(sn.avaliacao.metricas(y, comparacao["teste"]["v1"]["pred"])["acuracia"])
    assert acuracia_v1 < acuracia, (
        f"v1 tem acurácia {acuracia_v1:.4f}, abaixo do sempre-zero ({acuracia:.4f}) — "
        "e ainda assim é o modelo que pega as falhas"
    )


def test_v2_ganha_acuracia_sobre_v1():
    """Confirma os +3,5 pp que a equipe usou para decidir.

    **Único teste deste arquivo lido COM vazamento**, de propósito: é a reprodução do número
    da empresa, medido como a empresa mediu. O trabalho não contesta o número — contesta a
    métrica. Ver `evidencias/linha-de-base.md`.
    """
    lote = sn.dados.carregar("teste")
    y, _, pred_v1 = harness.prever_com_vazamento(lote, "v1")
    _, _, pred_v2 = harness.prever_com_vazamento(lote, "v2")

    a1 = float(sn.avaliacao.metricas(y, pred_v1)["acuracia"])
    a2 = float(sn.avaliacao.metricas(y, pred_v2)["acuracia"])

    assert a2 > a1
    assert 100 * (a2 - a1) == pytest.approx(3.48, abs=0.05), (
        f"acurácia v1={a1:.4f} v2={a2:.4f}, diferença {100 * (a2 - a1):+.2f} pp"
    )


@pytest.mark.defeito
@pytest.mark.xfail(
    strict=True,
    reason="D11 — a v2 perde 23,97 pp de recall: 157 falhas reais a mais que a v1 deixa passar",
)
def test_v2_nao_regride_recall_em_relacao_a_v1(comparacao):
    """O recall da v2 deveria ser pelo menos o da v1 — é a métrica que a planta compra."""
    dados = comparacao["teste"]
    r1 = _recall(dados["y"], dados["v1"]["pred"])
    r2 = _recall(dados["y"], dados["v2"]["pred"])

    assert r2 >= r1, (
        f"recall v1={r1:.4f}, v2={r2:.4f}: a v2 perde {100 * (r1 - r2):.2f} pp de recall — "
        f"deixa de pegar {int(round((r1 - r2) * dados['y'].sum()))} falhas reais a mais que a v1"
    )


def test_intervalo_pareado_da_diferenca_de_recall_nao_contem_zero(comparacao, n_boot, medicoes):
    """O IC pareado do Δrecall, reamostrando os MESMOS índices para v1 e v2 (aula 4).

    A ordem dos argumentos é `(v1, v2)` e o intervalo é de `recall(v1) − recall(v2)`:
    `lo > 0` ⇒ v1 melhor (SPEC §5).
    """
    dados = comparacao["teste"]
    lo, hi = estatistica.bootstrap_ci_pareado(
        dados["y"], dados["v1"]["pred"], dados["v2"]["pred"], _recall, n_boot=n_boot
    )

    assert not (lo <= 0 <= hi), f"IC [{lo:.4f}, {hi:.4f}] contém zero: diferença não significativa"
    assert estatistica.veredito(lo, hi) == "a_melhor", (
        f"IC [{lo:.4f}, {hi:.4f}] não aponta a v1 como melhor"
    )
    assert lo == pytest.approx(0.2075, abs=0.01)
    assert hi == pytest.approx(0.2698, abs=0.01)

    medicoes["v1_v2"]["ic_recall"] = [round(lo, 6), round(hi, 6)]


def test_mcnemar_exato_acusa_diferenca_entre_v1_e_v2(comparacao, medicoes):
    """McNemar exato sobre as falhas reais: entre v1 e v2, quem pega o motor que o outro perde?

    **Restrito aos positivos reais**, e não ao lote inteiro, porque é essa a pergunta que o IC
    pareado do recall faz. Ver a nota em `docs/decisoes.md`: o McNemar global responde sobre
    acurácia e dá o veredito oposto.
    """
    dados = comparacao["teste"]
    y = dados["y"]
    falhas = y == 1

    n01, n10, p = estatistica.mcnemar(y[falhas], dados["v1"]["pred"][falhas], dados["v2"]["pred"][falhas])

    assert p < ALPHA, f"p = {p:.4g} não acusa diferença ao nível de {ALPHA}"
    assert n10 > n01, (
        f"n10={n10} (v1 pega, v2 perde) deveria superar n01={n01} (v2 pega, v1 perde)"
    )
    assert n01 == 0, (
        f"n01={n01}: existe falha real que a v2 pega e a v1 perde — o achado de que as "
        "capturas da v2 são subconjunto das da v1 deixou de valer"
    )

    medicoes["v1_v2"]["mcnemar_p"] = p
    medicoes["v1_v2"]["discordantes"] = {"n01": n01, "n10": n10}


def test_mcnemar_concorda_com_o_intervalo_pareado(comparacao, n_boot):
    """Os dois métodos, feita a mesma pergunta, têm de dar o mesmo veredito.

    A ressalva não é decorativa: **feita a mesma pergunta**. O McNemar global compara acerto
    bruto, isto é, acurácia, e aponta a v2; o IC pareado do recall aponta a v1. Não é
    contradição, são perguntas diferentes — e foi só por medir as duas que isso apareceu.
    """
    dados = comparacao["teste"]
    y, falhas = dados["y"], dados["y"] == 1
    pred1, pred2 = dados["v1"]["pred"], dados["v2"]["pred"]

    lo, hi = estatistica.bootstrap_ci_pareado(y, pred1, pred2, _recall, n_boot=n_boot)
    n01, n10, p = estatistica.mcnemar(y[falhas], pred1[falhas], pred2[falhas])

    veredito_ic = estatistica.veredito(lo, hi)
    veredito_mcnemar = "a_melhor" if (p < ALPHA and n10 > n01) else "inconclusivo"

    assert veredito_ic == veredito_mcnemar == "a_melhor", (
        f"IC [{lo:.4f}, {hi:.4f}] diz {veredito_ic}; "
        f"McNemar (n01={n01}, n10={n10}, p={p:.4g}) diz {veredito_mcnemar}"
    )


@pytest.mark.parametrize(
    "conjunto",
    [
        # `teste` PASSA: como ranqueadora, a v2 é melhor ali (+9,07 pp de PR-AUC).
        # A vantagem some em produção. Marcar a função inteira daria XPASS em [teste]
        # e derrubaria a suíte (padrão de D17, `docs/decisoes.md`).
        "teste",
        pytest.param(
            "producao",
            marks=[
                pytest.mark.defeito,
                pytest.mark.xfail(
                    strict=True,
                    reason="D11 — em produção a PR-AUC da v2 fica 0,54 pp abaixo da v1",
                ),
            ],
        ),
    ],
)
def test_pr_auc_da_v2_nao_e_pior_que_a_da_v1(comparacao, conjunto):
    """PR-AUC por versão — a métrica de ranking que não depende do limiar."""
    dados = comparacao[conjunto]
    ap1 = metricas.average_precision(dados["y"], dados["v1"]["proba"])
    ap2 = metricas.average_precision(dados["y"], dados["v2"]["proba"])

    assert ap2 >= ap1, (
        f"{conjunto}/sem vazamento: PR-AUC v1={ap1:.4f}, v2={ap2:.4f} "
        f"({100 * (ap2 - ap1):+.2f} pp)"
    )


def test_f2_favorece_a_versao_com_mais_recall(comparacao):
    """F2 (β=2, recall pesa 4×) inverte o ranking que a acurácia produz."""
    dados = comparacao["teste"]
    y = dados["y"]

    f2_v1 = metricas.fbeta(y, dados["v1"]["pred"], beta=2.0)
    f2_v2 = metricas.fbeta(y, dados["v2"]["pred"], beta=2.0)
    ac_v1 = float(sn.avaliacao.metricas(y, dados["v1"]["pred"])["acuracia"])
    ac_v2 = float(sn.avaliacao.metricas(y, dados["v2"]["pred"])["acuracia"])

    assert ac_v2 > ac_v1, "premissa: a acurácia prefere a v2"
    assert f2_v1 > f2_v2, "F2 tem de preferir a v1, que é a de mais recall"
    assert f2_v1 == pytest.approx(0.7346, abs=1e-3)
    assert f2_v2 == pytest.approx(0.6510, abs=1e-3)


def test_acuracia_nao_separa_a_versao_boa_da_ruim(comparacao):
    """Oráculo fraco vs forte (aula 6): a acurácia aprova quem perde recall.

    O oráculo **fraco** é "a acurácia subiu": aprova a v2. O **forte** é "não deixa de pegar
    falha": reprova. Um teste escrito com o oráculo fraco teria passado na promoção da v2 —
    é literalmente o que aconteceu na Nortemec.
    """
    dados = comparacao["teste"]
    y = dados["y"]

    def oraculo_fraco(pred_novo, pred_velho) -> bool:
        m = sn.avaliacao.metricas
        return m(y, pred_novo)["acuracia"] >= m(y, pred_velho)["acuracia"]

    def oraculo_forte(pred_novo, pred_velho) -> bool:
        return _recall(y, pred_novo) >= _recall(y, pred_velho)

    v1, v2 = dados["v1"]["pred"], dados["v2"]["pred"]

    assert oraculo_fraco(v2, v1), "o oráculo fraco aprova a promoção da v2"
    assert not oraculo_forte(v2, v1), "o oráculo forte a reprova"
