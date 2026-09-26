"""Lotes sintéticos determinísticos.

Os CSVs do SUT servem para medir o mundo como ele é; a fábrica serve para construir o
caso exato que um teste precisa — um furo no historiador, uma leitura reenviada, um
lote de uma linha só — sem depender de o dado real por acaso conter aquilo.

**Toda função é determinística por semente** (SPEC S13): mesma semente, mesmo lote,
byte a byte. Nenhuma usa o relógio nem o RNG global do numpy.

Os lotes saem no formato **cru**, do jeito que `dados.carregar` devolve: é
`preprocessamento.limpar` que converte tipos. Todos os valores nascem dentro da ficha
técnica, para que qualquer violação num teste seja a que o teste injetou.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .ficha import FICHA, FATOR_PSI_POR_BAR, OPERADORES, TURNOS

INICIO_PADRAO = "2026-01-01 00:00:00"


def _nome_maquina(i: int) -> str:
    return f"M{i + 1:02d}"


def lote(
    n_maquinas: int = 3,
    n_horas: int = 48,
    seed: int = 42,
    inicio: str = INICIO_PADRAO,
    prevalencia: float = 0.15,
) -> pd.DataFrame:
    """Lote cru com grade horária contínua por motor, tudo dentro da ficha.

    `n_maquinas` × `n_horas` linhas, ordenadas por motor e por hora.
    """
    rng = np.random.default_rng(seed)
    carimbos = pd.date_range(inicio, periods=n_horas, freq="h")

    quadros = []
    for i in range(n_maquinas):
        n = n_horas
        quadro = pd.DataFrame(
            {
                "timestamp": carimbos.astype(str),
                "id_maquina": _nome_maquina(i),
                "idade_equipamento_meses": int(rng.integers(6, 181)),
                "id_operador": rng.choice(OPERADORES, size=n),
                "turno": rng.choice(TURNOS, size=n),
                "temperatura_c": rng.uniform(55.0, 85.0, size=n),
                "vibracao_rms": rng.uniform(2.0, 7.0, size=n),
                "pressao": rng.uniform(3.2, 4.3, size=n),
                "unidade_pressao": "bar",
                "corrente_a": rng.uniform(14.0, 28.0, size=n),
                "rpm": rng.uniform(1660.0, 1790.0, size=n),
                "horas_operacao": np.arange(n, dtype=float) + float(rng.integers(0, 5000)),
                "falha_72h": (rng.random(n) < prevalencia).astype(int),
            }
        )
        quadros.append(quadro)

    return pd.concat(quadros, ignore_index=True)


def com_dropout_de_vibracao(df: pd.DataFrame, fracao: float = 0.1, seed: int = 42) -> pd.DataFrame:
    """Apaga `fracao` das leituras de vibração — o dropout que o README documenta."""
    rng = np.random.default_rng(seed)
    saida = df.copy()
    alvo = rng.random(len(saida)) < fracao
    saida.loc[alvo, "vibracao_rms"] = np.nan
    return saida


def com_linhas_em_psi(df: pd.DataFrame, fracao: float = 0.3, seed: int = 42) -> pd.DataFrame:
    """Converte `fracao` das linhas para psi, marcando `unidade_pressao`.

    O valor físico não muda: só a unidade em que ele é reportado. É exatamente o que
    um CLP de outro fabricante faria — e o que o SUT ignora (D03).
    """
    rng = np.random.default_rng(seed)
    saida = df.copy()
    alvo = rng.random(len(saida)) < fracao
    saida.loc[alvo, "pressao"] = saida.loc[alvo, "pressao"] * FATOR_PSI_POR_BAR
    saida.loc[alvo, "unidade_pressao"] = "psi"
    return saida


def com_furo_no_historiador(
    df: pd.DataFrame, id_maquina: str, a_partir_da_hora: int, horas: int = 5
) -> pd.DataFrame:
    """Remove `horas` leituras consecutivas de um motor — buraco de coleta."""
    saida = df.copy()
    do_motor = saida.index[saida["id_maquina"] == id_maquina]
    if a_partir_da_hora + horas > len(do_motor):
        raise ValueError(
            f"furo de {horas}h a partir de {a_partir_da_hora} não cabe em "
            f"{len(do_motor)} leituras de {id_maquina}"
        )
    remover = do_motor[a_partir_da_hora : a_partir_da_hora + horas]
    return saida.drop(index=remover).reset_index(drop=True)


def com_leitura_duplicada(df: pd.DataFrame, posicao: int = 0) -> pd.DataFrame:
    """Reenvia uma leitura: a mesma `(id_maquina, timestamp)` aparece duas vezes."""
    saida = df.copy()
    linha = saida.iloc[[posicao]]
    return pd.concat([saida, linha], ignore_index=True)


def com_leitura_fora_de_faixa(
    df: pd.DataFrame, coluna: str, valor: float, posicao: int = 0
) -> pd.DataFrame:
    """Injeta uma leitura fisicamente impossível numa coluna da ficha."""
    if coluna not in FICHA:
        raise ValueError(f"coluna fora da ficha técnica: {coluna!r}")
    saida = df.copy()
    saida.loc[saida.index[posicao], coluna] = valor
    return saida


def perturbar_apenas_o_futuro(
    df: pd.DataFrame,
    id_maquina: str,
    hora: int,
    coluna: str = "temperatura_c",
    delta: float = 10.0,
) -> pd.DataFrame:
    """Altera **somente** as leituras posteriores a `hora`, para um motor.

    É o insumo do teste-estrela do vazamento temporal (D01): uma feature de `t`
    calculada corretamente não pode se mexer quando só `t+1, t+2, …` mudam. O oráculo
    é de perturbação, e não de valor esperado, justamente porque não depende do offset
    de janela par do pandas (SPEC P6).
    """
    saida = df.copy()
    do_motor = saida.index[saida["id_maquina"] == id_maquina]
    if hora >= len(do_motor):
        raise ValueError(f"hora {hora} fora do lote de {id_maquina} ({len(do_motor)} leituras)")
    futuro = do_motor[hora + 1 :]
    saida.loc[futuro, coluna] = saida.loc[futuro, coluna] + delta
    return saida


def lote_de_uma_linha(seed: int = 42) -> pd.DataFrame:
    """Uma leitura só — o caso de uso do painel da sala de controle."""
    return lote(n_maquinas=1, n_horas=1, seed=seed)


def lote_de_um_motor(n_horas: int = 48, seed: int = 42) -> pd.DataFrame:
    return lote(n_maquinas=1, n_horas=n_horas, seed=seed)


def lote_vazio() -> pd.DataFrame:
    """Zero linhas, colunas certas."""
    return lote(n_maquinas=1, n_horas=1).iloc[0:0].reset_index(drop=True)
