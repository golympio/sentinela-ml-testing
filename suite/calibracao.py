"""Calibração: a probabilidade quer dizer o que diz?

A planta não consome só a decisão. O guia do aluno pede, literalmente, comparar a
probabilidade média prevista em cada faixa com a frequência de falha observada naquela
faixa — porque é assim que uma equipe de manutenção **prioriza**: se o painel diz "85 % de
chance de falha" em dez motores, espera-se que cerca de oito falhem. Se falham três, o
número é um ranking disfarçado de probabilidade, e qualquer decisão de custo tomada sobre
ele está errada.

Três medidas, da mais grossa para a mais informativa:

- **Brier** — erro quadrático médio da probabilidade. Um número só, bom para comparar duas
  versões, mas mistura calibração com poder de discriminação: um modelo que sempre diz a
  prevalência é perfeitamente calibrado e inútil, e ainda assim tem Brier baixo.
- **ECE** — o desvio médio entre confiança e acerto, ponderado pela massa de cada faixa.
  Isola a calibração, que é o que aqui interessa.
- **curva de confiabilidade** — o detalhe por faixa, que diz **onde** o modelo mente. É a
  tabela que vai para o relatório; as duas anteriores são resumos dela.

**Faixas de largura fixa, não por quantil.** Com probabilidades extremas — que é o que uma
floresta profunda sem reponderação produz (D12) — os quantis colapsariam quase tudo numa
faixa só e esconderiam exatamente o defeito que estamos medindo. Largura fixa mantém as dez
faixas comparáveis entre v1 e v2, que é o que o relatório precisa.
"""
from __future__ import annotations

import numpy as np


def _valida(y, proba) -> tuple[np.ndarray, np.ndarray]:
    y = np.asarray(y, dtype=float)
    proba = np.asarray(proba, dtype=float)
    if y.shape != proba.shape:
        raise ValueError(f"tamanhos diferentes: y={y.shape}, proba={proba.shape}")
    if y.size == 0:
        raise ValueError("vetor vazio")
    fora = set(np.unique(y)) - {0.0, 1.0}
    if fora:
        raise ValueError(f"y deve ser binário; encontrado {sorted(fora)}")
    if np.any((proba < 0.0) | (proba > 1.0)):
        raise ValueError("proba fora de [0, 1]: não é probabilidade")
    return y, proba


def brier(y, proba) -> float:
    """Erro quadrático médio entre a probabilidade prevista e o resultado observado."""
    y, proba = _valida(y, proba)
    return float(np.mean((proba - y) ** 2))


def _mascara_da_faixa(proba: np.ndarray, bordas: np.ndarray, i: int) -> np.ndarray:
    """Faixas `(lo, hi]`, com a primeira fechada à esquerda para não perder `proba == 0`."""
    lo, hi = bordas[i], bordas[i + 1]
    if i == 0:
        return (proba >= lo) & (proba <= hi)
    return (proba > lo) & (proba <= hi)


def bins_de_confiabilidade(y, proba, faixas: int = 10) -> list[dict]:
    """A curva de confiabilidade como tabela. Uma entrada por faixa **não vazia**.

    Cada entrada traz `faixa` (o par de bordas), `n`, `confianca` (probabilidade média
    prevista), `observado` (frequência de falha medida) e `gap` (`confianca − observado`,
    positivo quando o modelo está **superconfiante**).

    Faixas vazias são omitidas em vez de virarem zeros: uma faixa sem nenhuma leitura não é
    evidência de calibração perfeita, e somá-la como gap 0 melhoraria o ECE de graça.
    """
    y, proba = _valida(y, proba)
    if faixas < 1:
        raise ValueError(f"faixas deve ser >= 1, recebido {faixas}")

    bordas = np.linspace(0.0, 1.0, faixas + 1)
    tabela = []
    for i in range(faixas):
        dentro = _mascara_da_faixa(proba, bordas, i)
        if not dentro.any():
            continue
        confianca = float(proba[dentro].mean())
        observado = float(y[dentro].mean())
        tabela.append(
            {
                "faixa": (float(bordas[i]), float(bordas[i + 1])),
                "n": int(dentro.sum()),
                "confianca": confianca,
                "observado": observado,
                "gap": confianca - observado,
            }
        )
    return tabela


def ece(y, proba, faixas: int = 10) -> float:
    """Expected Calibration Error: média dos `|gap|` ponderada pela massa de cada faixa.

    Lê-se em pontos de probabilidade: ECE de 0,12 significa que, em média, a confiança
    anunciada está 12 pontos longe da frequência observada.
    """
    y, proba = _valida(y, proba)
    total = float(y.size)
    return float(
        sum(b["n"] / total * abs(b["gap"]) for b in bins_de_confiabilidade(y, proba, faixas))
    )


def curva_em_ascii(tabela: list[dict], largura: int = 40) -> str:
    """A curva de confiabilidade em texto, para colar no relatório.

    Duas barras por faixa: `conf` é o que o modelo prometeu, `obs` é o que aconteceu. Barras
    desalinhadas são o defeito visível a olho nu.
    """
    linhas = [f"{'faixa':>12} {'n':>6}  {'conf':>6} {'obs':>6}  {'gap':>7}", "-" * 62]
    for b in tabela:
        lo, hi = b["faixa"]
        barra_conf = "#" * int(round(b["confianca"] * largura))
        barra_obs = "=" * int(round(b["observado"] * largura))
        linhas.append(
            f"{lo:.1f}–{hi:.1f}".rjust(12)
            + f" {b['n']:>6}  {b['confianca']:>6.3f} {b['observado']:>6.3f}  {b['gap']:>+7.3f}"
        )
        linhas.append(" " * 21 + "conf " + barra_conf)
        linhas.append(" " * 21 + "obs  " + barra_obs)
    return "\n".join(linhas)
