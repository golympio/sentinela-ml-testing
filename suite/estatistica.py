"""Incerteza: bootstrap pareado e McNemar exato.

Uma diferença de métrica entre dois modelos, sozinha, não diz nada: medida em outra
amostra ela seria outra. Este módulo existe para que toda afirmação de "a v1 é melhor
que a v2" venha com o intervalo que a sustenta — ou com a admissão de que não dá para
decidir.

**Convenção de sinal (SPEC §5, travada em `docs/decisoes.md`).** A diferença é sempre
`métrica(a) − métrica(b)`, e nas comparações deste projeto **a = v1** e **b = v2**.
Daí a regra de leitura:

| intervalo | leitura |
|---|---|
| `lo > 0` | **a** (v1) é melhor, com significância |
| `hi < 0` | **b** (v2) é melhor, com significância |
| `lo <= 0 <= hi` | inconclusivo |

`inconclusivo` **não** é equivalência: é a constatação de que esta amostra não separa os
dois. Dizer "são equivalentes" a partir de um intervalo que contém zero é a leitura errada
mais comum de um teste de hipótese.

> **Armadilha que nenhum teste pega sozinho.** Inverter a ordem dos argumentos inverte o
> veredito do relatório e o intervalo continua excluindo zero — só muda de lado, e a suíte
> segue verde. Por isso o teste de referência asserta o **lado** do intervalo contra dois
> modelos sintéticos de qualidade conhecida, e não apenas a ordem dos argumentos.

Dois métodos, de propósito (o enunciado aceita um ou outro; fazemos os dois e exigimos que
concordem):

- **bootstrap pareado** — reamostra **os mesmos índices** para A e para B (aula 4). Reamostrar
  independentemente mediria a diferença entre duas amostras diferentes, que é maior que a
  diferença entre os dois modelos na mesma amostra, e alargaria o intervalo sem motivo;
- **McNemar exato** — olha só as linhas em que os dois discordam, que é onde a informação
  sobre a diferença está. Exato por `binomtest`, não a aproximação qui-quadrado, porque a
  aproximação é ruim justamente quando há poucos discordantes (SPEC D7).

Nunca assertamos o valor de um p (SPEC D8): asserta-se o **veredito** (`p < alpha`), que é o
que o relatório afirma. O p em si vai para `medicoes.json` como número medido.
"""
from __future__ import annotations

from collections import Counter
from typing import Callable

import numpy as np
from scipy.stats import binomtest

# Quantas reamostragens por bloco de índices. O bootstrap é vetorizado em blocos para
# não materializar `n_boot × n` de uma vez: com n_boot=2000 e n=4200 isso seria 67 MB de
# int64 num array só. Se o orçamento de tempo de S11 apertar, reduza ESTE número antes de
# reduzir `n_boot` — menos reamostragens significam um intervalo pior estimado, enquanto
# um bloco menor só troca memória por chamadas.
BLOCO = 200


def _valida_par(y, pred_a, pred_b) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    y = np.asarray(y, dtype=int)
    a = np.asarray(pred_a, dtype=int)
    b = np.asarray(pred_b, dtype=int)
    if not (y.shape == a.shape == b.shape):
        raise ValueError(f"tamanhos diferentes: y={y.shape}, a={a.shape}, b={b.shape}")
    if y.size == 0:
        raise ValueError("vetor vazio")
    return y, a, b


def _percentis(amostras: np.ndarray, ci: float) -> tuple[float, float]:
    if not 0.0 < ci < 1.0:
        raise ValueError(f"ci deve estar em (0, 1), recebido {ci}")
    alpha = 1.0 - ci
    lo, hi = np.percentile(amostras, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return float(lo), float(hi)


def _blocos_de_indices(rng, n: int, n_boot: int, bloco: int = BLOCO):
    """Gera matrizes `(k, n)` de índices reamostrados com reposição, k <= bloco."""
    if n_boot < 1:
        raise ValueError(f"n_boot deve ser >= 1, recebido {n_boot}")
    restante = n_boot
    while restante > 0:
        k = min(bloco, restante)
        yield rng.integers(0, n, size=(k, n))
        restante -= k


def bootstrap_ci(
    y,
    pred,
    metric_fn: Callable[[np.ndarray, np.ndarray], float],
    n_boot: int = 1000,
    ci: float = 0.95,
    seed: int = 42,
) -> tuple[float, float]:
    """Intervalo de confiança percentil para `metric_fn(y, pred)`.

    A mesma semente devolve o mesmo intervalo: a única fonte de aleatoriedade da suíte é
    esta reamostragem (SPEC P7), logo ela é integralmente controlável.
    """
    y, pred, _ = _valida_par(y, pred, pred)
    rng = np.random.default_rng(seed)
    n = y.size

    amostras = [
        metric_fn(y[linha], pred[linha])
        for indices in _blocos_de_indices(rng, n, n_boot)
        for linha in indices
    ]
    return _percentis(np.asarray(amostras, dtype=float), ci)


def bootstrap_ci_pareado(
    y,
    pred_a,
    pred_b,
    metric_fn: Callable[[np.ndarray, np.ndarray], float],
    n_boot: int = 1000,
    ci: float = 0.95,
    seed: int = 42,
) -> tuple[float, float]:
    """IC percentil de `metric_fn(a) − metric_fn(b)`, reamostrando os MESMOS índices.

    Nas comparações deste projeto **a = v1** e **b = v2** (SPEC §5). Ver a regra de leitura
    no topo do módulo, e `veredito()` para aplicá-la sem reescrevê-la.

    Modelos idênticos devolvem um intervalo degenerado em zero — é o que prova que os
    índices são de fato compartilhados. Com reamostragem independente o intervalo teria
    largura, apesar de a diferença ser identicamente nula.
    """
    y, a, b = _valida_par(y, pred_a, pred_b)
    rng = np.random.default_rng(seed)
    n = y.size

    diferencas = [
        metric_fn(y[linha], a[linha]) - metric_fn(y[linha], b[linha])
        for indices in _blocos_de_indices(rng, n, n_boot)
        for linha in indices
    ]
    return _percentis(np.asarray(diferencas, dtype=float), ci)


def veredito(lo: float, hi: float) -> str:
    """Aplica a regra de leitura do módulo: `a_melhor` | `b_melhor` | `inconclusivo`.

    Existe para que a regra viva num lugar só. Reescrevê-la em cada teste é exatamente o
    mecanismo que produziu, uma vez, um veredito invertido neste projeto.
    """
    if lo > 0:
        return "a_melhor"
    if hi < 0:
        return "b_melhor"
    return "inconclusivo"


def mcnemar(y, pred_a, pred_b) -> tuple[int, int, float]:
    """McNemar exato sobre os discordantes. Devolve `(n01, n10, p)`.

    - `n10` — linhas em que **a** acerta e **b** erra;
    - `n01` — linhas em que **a** erra e **b** acerta.

    A hipótese nula é que os dois erros são igualmente prováveis, isto é, que os
    discordantes se dividem meio a meio: `binomtest(n01, n01 + n10, 0.5)` bilateral. As
    linhas em que ambos acertam ou ambos erram não entram — não carregam informação sobre
    a *diferença* entre os modelos, e incluí-las só diluiria o sinal.

    Sem nenhum discordante o teste é vacuamente nulo e devolvemos `p = 1.0`: não há
    evidência de diferença porque não há diferença observada. `binomtest` com `n = 0`
    levantaria.
    """
    y, a, b = _valida_par(y, pred_a, pred_b)
    acerta_a = a == y
    acerta_b = b == y

    n10 = int(np.sum(acerta_a & ~acerta_b))
    n01 = int(np.sum(~acerta_a & acerta_b))

    if n01 + n10 == 0:
        return 0, 0, 1.0
    p = float(binomtest(n01, n01 + n10, 0.5, alternative="two-sided").pvalue)
    return n01, n10, p


def estabilidade_do_veredito(fn: Callable[[int], str], sementes: int = 200) -> dict:
    """Roda `fn(semente)` com `sementes` sementes e conta quantas vezes cada veredito saiu.

    Um veredito que depende da semente não é um resultado, é um sorteio — e o relatório
    não pode afirmá-lo. Mitiga o risco de flaky registrado no PRD §8.

    Devolve `{veredito, concordantes, sementes, contagem}`, com `veredito` o mais frequente
    e `concordantes` quantas sementes o produziram.
    """
    if sementes < 1:
        raise ValueError(f"sementes deve ser >= 1, recebido {sementes}")
    contagem = Counter(fn(s) for s in range(sementes))
    vencedor, quantas = contagem.most_common(1)[0]
    return {
        "veredito": vencedor,
        "concordantes": int(quantas),
        "sementes": int(sementes),
        "contagem": dict(sorted(contagem.items())),
    }
