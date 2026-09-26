"""Prever com e sem o rótulo dentro da entrada.

O SUT recalcula `maquina_risco` a partir de `falha_72h` sempre que a coluna está presente
(`features._risco_por_maquina`). Como o alvo vem no CSV dos três conjuntos — inclusive
`producao` (SPEC P8) —, **toda métrica já publicada sobre o Sentinela foi medida com o
gabarito dentro da entrada**. Este módulo separa os dois modos para que a diferença possa
ser medida em vez de suposta.

**A variante sem vazamento é uma simulação do serving, não o serving real.** Em produção o
rótulo simplesmente não existe ainda — a falha das próximas 72 h não aconteceu. Aqui nós o
removemos deliberadamente, e o relatório declara isso como simulação.

A ordem é obrigatória e não é intercambiável (SPEC P8):

1. `limpar` **com** o rótulo — `preprocessamento.limpar` descarta linhas (rpm < 1,0), então
   `y` precisa ser extraído do quadro **já limpo**, ou fica desalinhado com as predições;
2. extrair `y` do quadro limpo;
3. `construir` sobre um quadro **sem** a coluna `falha_72h`.

Inverter 1 e 3 daria um `y` de tamanho errado; pular o passo 3 é exatamente o defeito D02.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import sentinela as sn
from sentinela.modelo import LIMIAR_PADRAO

ALVO = "falha_72h"


def _y_e_features(lote: pd.DataFrame, *, vazar: bool) -> tuple[np.ndarray | None, pd.DataFrame]:
    """Limpa com o rótulo, extrai `y`, e constrói com ou sem a coluna de rótulo."""
    limpo = sn.preprocessamento.limpar(lote)

    y = limpo[ALVO].to_numpy(dtype=int) if ALVO in limpo.columns else None

    quadro = limpo if vazar else limpo.drop(columns=[ALVO], errors="ignore")
    X = sn.features.construir(quadro)
    return y, X


def _prever(
    lote: pd.DataFrame, versao: str, limiar: float, *, vazar: bool
) -> tuple[np.ndarray | None, np.ndarray, np.ndarray]:
    y, X = _y_e_features(lote, vazar=vazar)
    modelo = sn.modelo.carregar(versao)
    probabilidade = modelo.prever_proba(X)
    predicao = (probabilidade >= limiar).astype(int)
    return y, probabilidade, predicao


def prever_com_vazamento(
    lote: pd.DataFrame, versao: str = "v1", limiar: float = LIMIAR_PADRAO
) -> tuple[np.ndarray | None, np.ndarray, np.ndarray]:
    """Como o SUT faz hoje: o rótulo fica no quadro e `maquina_risco` é recalculada com ele.

    É o caminho por onde o próprio `scripts/treinar.py` passa — ver `docs/decisoes.md`, seção
    da intenção morta. Portanto não é um cenário hipotético: é como o modelo foi treinado e
    como as métricas publicadas foram medidas.
    """
    return _prever(lote, versao, limiar, vazar=True)


def prever_sem_vazamento(
    lote: pd.DataFrame, versao: str = "v1", limiar: float = LIMIAR_PADRAO
) -> tuple[np.ndarray | None, np.ndarray, np.ndarray]:
    """Simulação do serving: o rótulo é removido antes de construir as features.

    Sem a coluna, `_risco_por_maquina` cai na tabela congelada de `risco_maquina.json` — que
    é o que a planta teria em mãos na hora de decidir.
    """
    return _prever(lote, versao, limiar, vazar=False)


def maquina_risco(lote: pd.DataFrame, *, vazar: bool) -> np.ndarray:
    """A feature `maquina_risco` isolada, nos dois modos. Insumo dos testes de D02."""
    _, X = _y_e_features(lote, vazar=vazar)
    return X["maquina_risco"].to_numpy(dtype=float)
