"""Três detectores de drift, e o que cada um aceita não enxergar.

Produção não é o conjunto de teste, e nada no Sentinela observa isso. O ponto desta fase não
é "detectar drift": é mostrar que **escolher o detector é escolher o que se aceita não
enxergar** (aula 6).

- **diferença de médias** — barata e a que todo mundo implementa primeiro. Cega a qualquer
  mudança que preserve a média: uma distribuição que abre a cauda, ou que troca massa entre
  dois modos, passa batida.
- **KS** — compara as distribuições acumuladas inteiras, então enxerga mudança de forma. Em
  amostra grande acusa diferenças irrelevantes: com n = 4.200 por lado, um p minúsculo pode
  corresponder a um deslocamento sem nenhum efeito prático. **p pequeno não é efeito grande.**
- **PSI** — mede o deslocamento de massa entre faixas e vem com as faixas de leitura que a
  indústria usa (< 0,1 estável; 0,1–0,25 atenção; > 0,25 drift). É o único dos três que fala
  em **tamanho** do efeito, e por isso é o que entra na conversa com a operação.

Nenhum deles é o certo. Os três juntos, com os números à vista, são o resultado.

**Bordas por quantil no PSI** (e não largura fixa): com sensores em escalas muito diferentes
— temperatura em dezenas, vibração em unidades — faixas de largura fixa poriam quase toda a
massa numa faixa só e o índice ficaria insensível. As bordas saem do **baseline**, que é a
referência contra a qual produção é comparada.
"""
from __future__ import annotations

import numpy as np
from scipy.stats import ks_2samp

# Faixas de leitura usuais do PSI. Não são lei, são convenção de indústria — e é por isso
# que elas aparecem aqui, nomeadas, em vez de soltas num assert.
PSI_ESTAVEL = 0.10
PSI_DRIFT = 0.25

# Piso que evita log(0) numa faixa sem massa. `1e-6` é pequeno o bastante para não mover o
# índice e grande o bastante para o log não explodir.
_PISO = 1e-6


def _limpa(x) -> np.ndarray:
    """Vetor 1-D float sem NaN. O dropout de vibração é real (SPEC D20) e não é drift."""
    x = np.asarray(x, dtype=float).ravel()
    return x[np.isfinite(x)]


def detectar_drift_media(baseline, producao, limiar: float = 0.10) -> dict:
    """Drift pela diferença relativa das médias.

    `limiar` é relativo à média do baseline — 0,10 = 10 %. Comparar em valor absoluto não
    serviria: 2 °C e 2 mm/s não são a mesma coisa.

    Devolve `{media_baseline, media_producao, delta_media, delta_relativo, drift}`.
    """
    b, p = _limpa(baseline), _limpa(producao)
    if b.size == 0 or p.size == 0:
        raise ValueError("série vazia depois de remover não-finitos")

    media_b, media_p = float(b.mean()), float(p.mean())
    delta = media_p - media_b
    relativo = abs(delta) / abs(media_b) if media_b else float("inf")
    return {
        "media_baseline": media_b,
        "media_producao": media_p,
        "delta_media": delta,
        "delta_relativo": relativo,
        "drift": bool(relativo > limiar),
    }


def detectar_drift_ks(baseline, producao, alpha: float = 0.01) -> dict:
    """Kolmogorov–Smirnov de duas amostras.

    Devolve `{estatistica, ks_p, drift}`. `estatistica` é a distância máxima entre as
    acumuladas — o **tamanho** do efeito, que o p sozinho não dá. Reportar os dois é o que
    impede a leitura "p = 1e-40, logo o drift é enorme".
    """
    b, p = _limpa(baseline), _limpa(producao)
    if b.size == 0 or p.size == 0:
        raise ValueError("série vazia depois de remover não-finitos")

    resultado = ks_2samp(b, p)
    return {
        "estatistica": float(resultado.statistic),
        "ks_p": float(resultado.pvalue),
        "drift": bool(resultado.pvalue < alpha),
    }


def psi(baseline, producao, faixas: int = 10) -> float:
    """Population Stability Index, com bordas por quantil do baseline.

    `PSI = Σ (p_prod − p_base) · ln(p_prod / p_base)`, simétrico por construção e sempre ≥ 0.
    Uma série comparada consigo mesma dá exatamente 0.
    """
    b, p = _limpa(baseline), _limpa(producao)
    if b.size == 0 or p.size == 0:
        raise ValueError("série vazia depois de remover não-finitos")
    if faixas < 2:
        raise ValueError(f"faixas deve ser >= 2, recebido {faixas}")

    bordas = np.quantile(b, np.linspace(0.0, 1.0, faixas + 1))
    bordas = np.unique(bordas)          # séries discretas geram quantis repetidos
    if bordas.size < 2:
        return 0.0                      # baseline constante: não há faixa que distinga nada
    bordas[0], bordas[-1] = -np.inf, np.inf

    cont_b, _ = np.histogram(b, bins=bordas)
    cont_p, _ = np.histogram(p, bins=bordas)

    prop_b = np.clip(cont_b / b.size, _PISO, None)
    prop_p = np.clip(cont_p / p.size, _PISO, None)

    return float(np.sum((prop_p - prop_b) * np.log(prop_p / prop_b)))


def classificar_psi(valor: float) -> str:
    """`estavel` | `atencao` | `drift`, pelas faixas usuais."""
    if valor < PSI_ESTAVEL:
        return "estavel"
    if valor < PSI_DRIFT:
        return "atencao"
    return "drift"


def medir(baseline, producao, limiar_media: float = 0.10, alpha: float = 0.01) -> dict:
    """Os três detectores de uma vez, no formato da chave `drift` de `medicoes.json` (C8)."""
    media = detectar_drift_media(baseline, producao, limiar_media)
    ks = detectar_drift_ks(baseline, producao, alpha)
    valor_psi = psi(baseline, producao)
    return {
        "delta_media": round(media["delta_media"], 6),
        "delta_relativo": round(media["delta_relativo"], 6),
        "media_acusa": media["drift"],
        "ks_estatistica": round(ks["estatistica"], 6),
        "ks_p": ks["ks_p"],
        "ks_acusa": ks["drift"],
        "psi": round(valor_psi, 6),
        "psi_classe": classificar_psi(valor_psi),
    }
