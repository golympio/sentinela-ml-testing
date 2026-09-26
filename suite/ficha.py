"""A ficha técnica do SUT como contrato executável.

O README do Sentinela declara faixa, unidade e ruído de cada sensor. Essa tabela é a
**única fonte de verdade** sobre o que é uma leitura válida (SPEC P9), então ela vira
dado aqui — não número solto espalhado em `assert`. Mudar a ficha passa a ser mudar
uma linha (SPEC D9).

Os validadores seguem o padrão da aula 3: **levantam `ValueError` com mensagem que
nomeia a coluna** e **retornam `True`** quando passam. Retornar `True` não é
decoração: permite encadear no teste e deixa explícito que "não levantou" é o
resultado esperado, não um silêncio acidental.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class FaixaSensor:
    """Uma linha da ficha técnica."""

    unidade: str
    minimo: float
    maximo: float
    ruido: float | None = None
    obrigatoria: bool = True


# Faixa de operação por coluna, exatamente como o README do SUT declara.
# `vibracao_rms` é a única não obrigatória: o README documenta dropout do sensor.
FICHA: dict[str, FaixaSensor] = {
    "temperatura_c": FaixaSensor("°C", 45.0, 95.0, ruido=1.0),
    "vibracao_rms": FaixaSensor("mm/s", 1.2, 8.0, obrigatoria=False),
    "pressao": FaixaSensor("bar", 3.0, 4.5),
    "corrente_a": FaixaSensor("A", 12.0, 30.0),
    "rpm": FaixaSensor("rpm", 1650.0, 1800.0),
    "idade_equipamento_meses": FaixaSensor("meses", 6.0, 180.0),
}

FATOR_PSI_POR_BAR = 14.5038
UNIDADES_PRESSAO = ("bar", "psi")
RUIDO_TEMPERATURA_C = 1.0

# Tipo esperado por coluna, no quadro **cru** (como `dados.carregar` devolve).
# "texto" cobre o object/str do pandas; "inteiro" e "real" cobrem as famílias numéricas.
TIPOS_ESPERADOS: dict[str, str] = {
    "timestamp": "texto",
    "id_maquina": "texto",
    "id_operador": "texto",
    "unidade_pressao": "texto",
    "idade_equipamento_meses": "inteiro",
    "turno": "inteiro",
    "falha_72h": "inteiro",
    "temperatura_c": "real",
    "vibracao_rms": "real",
    "pressao": "real",
    "corrente_a": "real",
    "rpm": "real",
    "horas_operacao": "real",
}

OPERADORES = tuple(f"OP-{n:02d}" for n in range(1, 13))
PADRAO_ID_OPERADOR = r"^OP-\d{2}$"
TURNOS = (1, 2, 3)
ALVO = "falha_72h"
VALORES_ALVO = (0, 1)
CHAVE = ("id_maquina", "timestamp")

# `rpm` mínimo que o SUT usa para decidir "eixo girando" (preprocessamento.RPM_MINIMO
# é 1.0). A ficha diz 1.650: qualquer coisa entre 1 e 1.650 atravessa o SUT como se
# fosse medição válida. A distância entre estes dois números é o defeito D05.
RPM_EIXO_PARADO_SEGUNDO_O_SUT = 1.0


def converter_pressao_para_bar(df: pd.DataFrame) -> pd.Series:
    """Pressão em bar, respeitando `unidade_pressao` linha a linha.

    O SUT normaliza `unidade_pressao` para minúsculo e **nunca a usa** para converter
    (defeito D03). Esta função é o que o SUT deveria fazer, e serve de oráculo.
    """
    for coluna in ("pressao", "unidade_pressao"):
        if coluna not in df.columns:
            raise ValueError(f"coluna ausente para converter pressão: {coluna!r}")
    unidade = df["unidade_pressao"].astype(str).str.strip().str.lower()
    pressao = df["pressao"].astype(float)
    return pressao.where(unidade != "psi", pressao / FATOR_PSI_POR_BAR)


def validar_schema(df: pd.DataFrame, colunas: tuple[str, ...]) -> bool:
    """Toda coluna esperada existe. Nomeia as que faltam."""
    faltando = [c for c in colunas if c not in df.columns]
    if faltando:
        raise ValueError(f"colunas ausentes no quadro: {sorted(faltando)}")
    return True


def validar_faixa(df: pd.DataFrame, coluna: str, valores: pd.Series | None = None) -> bool:
    """A coluna está dentro da faixa da ficha. Nomeia a coluna e conta as violações.

    `valores` permite validar uma versão derivada da coluna — é assim que a pressão é
    verificada **depois** de convertida para bar.
    """
    if coluna not in FICHA:
        raise ValueError(f"coluna fora da ficha técnica: {coluna!r}")
    faixa = FICHA[coluna]
    serie = df[coluna] if valores is None else valores
    serie = serie.astype(float)

    fora = serie.notna() & ~serie.between(faixa.minimo, faixa.maximo)
    if fora.any():
        raise ValueError(
            f"{coluna}: {int(fora.sum())} de {len(serie)} leituras fora da faixa "
            f"[{faixa.minimo}, {faixa.maximo}] {faixa.unidade} "
            f"(mín={serie.min():.4g}, máx={serie.max():.4g})"
        )
    return True


def validar_sem_faltantes(df: pd.DataFrame, coluna: str) -> bool:
    """A coluna não tem NaN. Nomeia a coluna e conta."""
    if coluna not in df.columns:
        raise ValueError(f"coluna ausente: {coluna!r}")
    ausentes = int(df[coluna].isna().sum())
    if ausentes:
        raise ValueError(f"{coluna}: {ausentes} de {len(df)} valores ausentes")
    return True


def validar_chave_unica(df: pd.DataFrame, colunas: tuple[str, ...] = CHAVE) -> bool:
    """A chave não se repete (`check_unique_ids` da aula 3)."""
    validar_schema(df, colunas)
    duplicadas = int(df.duplicated(list(colunas)).sum())
    if duplicadas:
        raise ValueError(
            f"chave {list(colunas)}: {duplicadas} linhas duplicadas de {len(df)}"
        )
    return True


def validar_unidade_pressao(df: pd.DataFrame) -> bool:
    """`unidade_pressao` só tem valores do domínio conhecido."""
    if "unidade_pressao" not in df.columns:
        raise ValueError("coluna ausente: 'unidade_pressao'")
    vistos = set(df["unidade_pressao"].astype(str).str.strip().str.lower().unique())
    desconhecidas = sorted(vistos - set(UNIDADES_PRESSAO))
    if desconhecidas:
        raise ValueError(
            f"unidade_pressao: valores fora do domínio {list(UNIDADES_PRESSAO)}: "
            f"{desconhecidas}"
        )
    return True


def validar_id_operador(df: pd.DataFrame) -> bool:
    """`id_operador` segue `OP-NN` e está entre OP-01 e OP-12."""
    if "id_operador" not in df.columns:
        raise ValueError("coluna ausente: 'id_operador'")
    serie = df["id_operador"].astype(str).str.strip().str.upper()
    fora_do_padrao = sorted(set(serie[~serie.str.match(PADRAO_ID_OPERADOR)]))
    if fora_do_padrao:
        raise ValueError(f"id_operador: fora do padrão {PADRAO_ID_OPERADOR}: {fora_do_padrao}")
    desconhecidos = sorted(set(serie) - set(OPERADORES))
    if desconhecidos:
        raise ValueError(f"id_operador: fora de OP-01..OP-12: {desconhecidos}")
    return True


def validar_dominio(df: pd.DataFrame, coluna: str, permitidos: tuple) -> bool:
    """A coluna só tem valores do conjunto permitido."""
    if coluna not in df.columns:
        raise ValueError(f"coluna ausente: {coluna!r}")
    vistos = set(df[coluna].dropna().unique())
    fora = sorted(vistos - set(permitidos))
    if fora:
        raise ValueError(f"{coluna}: valores fora de {list(permitidos)}: {fora}")
    return True


def validar_completude(df: pd.DataFrame, coluna: str, minimo: float) -> bool:
    """A fração de valores presentes na coluna é pelo menos `minimo`."""
    if coluna not in df.columns:
        raise ValueError(f"coluna ausente: {coluna!r}")
    if not 0.0 <= minimo <= 1.0:
        raise ValueError(f"completude mínima deve estar em [0, 1], recebido {minimo}")
    presente = float(df[coluna].notna().mean())
    if presente < minimo:
        raise ValueError(
            f"{coluna}: completude {presente:.4f} abaixo do mínimo exigido {minimo:.4f}"
        )
    return True


def colunas_obrigatorias() -> tuple[str, ...]:
    """Colunas da ficha que não admitem ausente."""
    return tuple(sorted(c for c, f in FICHA.items() if f.obrigatoria))


def _validar_regex_operador(valor: str) -> bool:
    return bool(re.match(PADRAO_ID_OPERADOR, valor))


def validar_tipo(df: pd.DataFrame, coluna: str) -> bool:
    """O dtype da coluna pertence à família que a ficha declara."""
    if coluna not in TIPOS_ESPERADOS:
        raise ValueError(f"coluna sem tipo declarado na ficha: {coluna!r}")
    if coluna not in df.columns:
        raise ValueError(f"coluna ausente: {coluna!r}")

    esperado = TIPOS_ESPERADOS[coluna]
    serie = df[coluna]
    familia = {
        "inteiro": pd.api.types.is_integer_dtype,
        "real": pd.api.types.is_numeric_dtype,
        "texto": lambda s: pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s),
    }[esperado]

    if not familia(serie):
        raise ValueError(
            f"{coluna}: esperado tipo {esperado}, encontrado dtype {serie.dtype}"
        )
    return True
