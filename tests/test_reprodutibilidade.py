"""O ambiente é o que a especificação diz que é.

Quatro testes que provam a fundação antes de qualquer teste de bloco: os
artefatos batem com o manifest (não batem: é o defeito D23), o SUT está no
commit pinado, as versões em runtime são as de `requirements.txt` e as 13
features estão na ordem conhecida. Se um destes falha, nenhuma medida da suíte
significa coisa alguma.
"""
from __future__ import annotations

import os
import pathlib
import re
import subprocess
from importlib import metadata

import pytest

import sentinela as sn

from scripts.smoke import DIVERGENCIAS_CONHECIDAS

pytestmark = [pytest.mark.unitario, pytest.mark.rapido]

RAIZ_SUT = pathlib.Path("/opt/sentinela")
RAIZ_SUITE = pathlib.Path(__file__).resolve().parents[1]

# A tupla literal esperada. Escrita à mão de propósito: comparar
# `ORDEM_FEATURES` consigo mesma não provaria nada, e `modelo.carregar` valida
# a sincronia entre esta ordem e a do artefato (SPEC P4).
ORDEM_FEATURES_ESPERADA = (
    "temp_media_6h",
    "temp_max_24h",
    "delta_temp_24h",
    "vib_media_6h",
    "vib_max_24h",
    "corrente_media_6h",
    "pressao",
    "rpm",
    "idade_equipamento_meses",
    "horas_operacao",
    "maquina_risco",
    "operador_senior",
    "turno",
)


@pytest.mark.defeito
@pytest.mark.xfail(
    strict=True,
    reason=(
        "D23 — manifest desatualizado no commit pinado: o sha256 dos três CSVs de "
        "dados/ e de artefatos/risco_maquina.json não bate com artefatos/manifest.json"
    ),
)
def test_artefatos_batem_com_o_manifest():
    """O README do SUT promete `[]`; o commit pinado entrega quatro divergências.

    Verificado em clone limpo (`git status --porcelain` vazio), portanto é defeito
    do SUT e não do nosso ambiente: os dados e a tabela de risco foram regerados
    sem que o manifest fosse reescrito. Os dois artefatos de modelo, esses, batem
    — é o que distingue D23 de uma corrupção de clone.
    """
    assert sn.artefatos.verificar_manifest() == []


def test_a_divergencia_do_manifest_e_exatamente_a_catalogada_em_d23():
    """Enquanto D23 existir, ele não pode crescer em silêncio.

    Este teste é verde de propósito: ele não afirma que o manifest está certo,
    afirma que o estrago é **exatamente** o conhecido. Se o SUT ganhar uma quinta
    divergência, ou perder uma das quatro, a suíte avisa aqui — e não no xfail
    acima, que continuaria falhando do mesmo jeito.
    """
    problemas = set(sn.artefatos.verificar_manifest())
    assert problemas == set(DIVERGENCIAS_CONHECIDAS)


def test_sut_esta_no_commit_pinado():
    esperado = os.environ.get("SENTINELA_REF", "")
    assert esperado, "SENTINELA_REF não está no ambiente do container"

    obtido = subprocess.run(
        ["git", "-C", str(RAIZ_SUT), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    assert obtido == esperado, (
        f"o SUT não está no commit pinado: esperado {esperado}, obtido {obtido}"
    )


def test_versoes_das_dependencias_batem_com_o_requirements():
    pinos = {}
    for linha in (RAIZ_SUITE / "requirements.txt").read_text(encoding="utf-8").splitlines():
        achado = re.match(r"^([A-Za-z0-9_.-]+)==([^\s#]+)", linha.strip())
        if achado:
            pinos[achado.group(1).lower()] = achado.group(2)

    assert pinos, "requirements.txt não tem nenhum pino `==`"

    em_runtime = {pacote: metadata.version(pacote) for pacote in pinos}
    assert em_runtime == pinos


def test_ordem_features_tem_as_treze_colunas_conhecidas():
    assert sn.features.ORDEM_FEATURES == ORDEM_FEATURES_ESPERADA
