"""Métricas de classe rara, em numpy puro.

`sn.avaliacao` expõe **somente** acurácia, precisão, recall e F1 (SPEC P1). Com prevalência
de ~15 %, acurácia premia quem não prevê falha nenhuma, e F1 pesa precisão e recall igual
quando a planta não os pesa igual: deixar de abrir uma ordem custa um motor queimado, abrir
uma a mais custa uma inspeção. Daí PR-AUC, F-beta e recall sob precisão mínima.

Sem scikit-learn, por decisão do projeto — e porque a inferência do SUT também é numpy puro,
então os números não dependem de nada além do que está pinado.

**Empates importam.** Com 60 e 80 árvores votando, muitas linhas recebem exatamente a mesma
probabilidade. A curva agrupa scores iguais num **único** ponto de corte: um limiar não
consegue separar duas linhas com o mesmo score, então tratá-las como cortes distintos
inventaria pontos que nenhum limiar realiza — e infla a PR-AUC.
"""
from __future__ import annotations

import numpy as np


def _valida(y, score_ou_pred) -> tuple[np.ndarray, np.ndarray]:
    y = np.asarray(y, dtype=int)
    v = np.asarray(score_ou_pred, dtype=float)
    if y.shape != v.shape:
        raise ValueError(f"tamanhos diferentes: y={y.shape}, outro={v.shape}")
    if y.size == 0:
        raise ValueError("vetor vazio")
    fora = set(np.unique(y)) - {0, 1}
    if fora:
        raise ValueError(f"y deve ser binário; encontrado {sorted(fora)}")
    return y, v


def curva_precisao_recall(y, score) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """`(precisao, recall, limiares)` em ordem crescente de recall.

    Scores iguais entram num único ponto de corte. Inclui o ponto de recall 0 com precisão 1
    como âncora esquerda, convenção usual para que a integral não dependa do primeiro corte.
    """
    y, score = _valida(y, score)
    positivos = int(y.sum())
    if positivos == 0:
        raise ValueError("não há positivos em y: precisão/recall são indefinidos")

    ordem = np.argsort(-score, kind="mergesort")   # estável: empates preservam a ordem
    y_ord, s_ord = y[ordem], score[ordem]

    vp = np.cumsum(y_ord)
    previstos = np.arange(1, len(y_ord) + 1)

    # último índice de cada bloco de score igual — o corte só existe no fim do bloco
    fim_do_bloco = np.r_[np.flatnonzero(np.diff(s_ord)), len(s_ord) - 1]

    precisao = vp[fim_do_bloco] / previstos[fim_do_bloco]
    recall = vp[fim_do_bloco] / positivos
    limiares = s_ord[fim_do_bloco]

    return np.r_[1.0, precisao], np.r_[0.0, recall], np.r_[np.inf, limiares]


def average_precision(y, score) -> float:
    """PR-AUC pela soma ponderada de Precisão(k) × ΔRecall(k) — sem interpolação.

    É a definição que não superestima: interpolar a curva PR entre pontos inventa desempenho
    que nenhum limiar entrega.
    """
    precisao, recall, _ = curva_precisao_recall(y, score)
    return float(np.sum(np.diff(recall) * precisao[1:]))


def fbeta(y, pred, beta: float = 2.0) -> float:
    """F-beta. `beta=2` pesa recall 4× mais que precisão (β²).

    Na planta: deixar de prever uma falha custa muito mais que uma inspeção desnecessária.
    """
    y, pred = _valida(y, pred)
    if beta <= 0:
        raise ValueError(f"beta deve ser positivo, recebido {beta}")
    pred = pred.astype(int)

    vp = float(((pred == 1) & (y == 1)).sum())
    fp = float(((pred == 1) & (y == 0)).sum())
    fn = float(((pred == 0) & (y == 1)).sum())

    if vp == 0.0:
        return 0.0
    precisao = vp / (vp + fp)
    recall = vp / (vp + fn)
    b2 = beta * beta
    return float((1 + b2) * precisao * recall / (b2 * precisao + recall))


def recall_com_precisao_minima(y, score, precisao_minima: float) -> tuple[float, float]:
    """Maior recall alcançável sem cair abaixo de `precisao_minima`, e o limiar que o entrega.

    É a pergunta que a manutenção faz de verdade: "quantas falhas eu pego, se eu aceito que no
    máximo X % das ordens abertas sejam em vão?". Devolve `(0.0, inf)` se nenhum corte atinge
    a precisão pedida.
    """
    if not 0.0 < precisao_minima <= 1.0:
        raise ValueError(f"precisao_minima deve estar em (0, 1], recebido {precisao_minima}")
    precisao, recall, limiares = curva_precisao_recall(y, score)

    viaveis = precisao >= precisao_minima
    viaveis[0] = False                      # a âncora (recall 0) não é um corte real
    if not viaveis.any():
        return 0.0, float("inf")
    melhor = int(np.argmax(np.where(viaveis, recall, -1.0)))
    return float(recall[melhor]), float(limiares[melhor])
