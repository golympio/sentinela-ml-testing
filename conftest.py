"""Fixtures de sessão, isolamento de estado global e despejo das medições.

Três responsabilidades:

1. **Reprodutibilidade** — semente única (`SUITE_SEED`) e um gerador novo por
   teste, para que a mesma semente produza os mesmos números (SPEC S13).
2. **Isolamento** — `features._RISCO_CONGELADO` é zerado antes e depois de
   cada teste e `modelo._CACHE` é vigiado, não limpo (SPEC S12 / D4).
3. **Medição** — o que os testes medem vai para `medicoes.json` no esquema de
   SPEC C8, escrito no fim da sessão.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
from importlib import metadata

import pytest

import sentinela as sn
from sentinela import features, modelo, pipeline

RAIZ_SUT = pathlib.Path("/opt/sentinela")
PACOTES_PINADOS = ("numpy", "pandas", "scipy", "pytest")

# Esquema de SPEC C8. As chaves nascem todas aqui para que `medicoes.json`
# tenha sempre a mesma forma, mesmo numa sessão que roda um subconjunto.
_MEDICOES: dict = {
    "sut": {},
    # Descritores dos três conjuntos, medidos por `test_contrato_dados.py`:
    # prevalência, taxa de dropout de vibração, proporção de linhas em psi, nº de linhas.
    # Extensão do esquema de C8 decidida na execução do HANDOFF 02 — o relatório precisa
    # desses números e não havia chave para eles.
    "contrato_dados": {},
    "linha_de_base": [],
    "v1_v2": {},
    "limiar": [],
    "flip": {},
    # Contrafactuais do Bloco C (HANDOFF 05): flip por versão de cada troca de um campo só,
    # mais a taxa de falha por operador — o confundidor de D06. Extensão do esquema de C8:
    # o relatório precisa dos três números, e `flip` é da varredura de amplitude (V9).
    "contrafactual": {},
    "drift": {},
    # Lista `{versao, feature, delta_medio}`. A chave `versao` foi acrescentada no HANDOFF
    # 05: o ranking difere entre v1 e v2 e um ranking sem versão não responde a nada.
    "sensibilidade": [],
}

_ambiente_cache: dict | None = None


def sha_do_sut() -> str:
    """SHA do clone do SUT, ou string vazia se não for um repositório Git."""
    try:
        saida = subprocess.run(
            ["git", "-C", str(RAIZ_SUT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return saida.stdout.strip()


def descrever_ambiente() -> dict:
    """SHA do SUT, versões em runtime e a PROCEDÊNCIA da rodada. Entra em medicoes.json.

    `semente` e `n_boot` não são decoração: qualquer `pytest` avulso regrava este arquivo,
    e o serviço `suite` roda com `SUITE_N_BOOT=1000` enquanto o alvo `evidencias` usa 2000.
    Sem registrar o parâmetro, uma rodada parcial substitui `v1_v2` por um intervalo de
    outra configuração **em silêncio** — foi o que aconteceu na execução do HANDOFF 06,
    e só apareceu porque alguém comparou o mtime dos sete artefatos de C7.

    Registrando, a divergência fica auditável: o relatório cita `sut.n_boot` ao lado do
    intervalo, e quem reproduzir vê na hora se está olhando a mesma rodada.
    """
    global _ambiente_cache
    if _ambiente_cache is None:
        _ambiente_cache = {
            "sha": sha_do_sut(),
            "ref_esperado": os.environ.get("SENTINELA_REF", ""),
            "versao_sentinela": sn.__version__,
            "versoes": {p: metadata.version(p) for p in PACOTES_PINADOS},
            "semente": int(os.environ.get("SUITE_SEED", "42")),
            "n_boot": int(os.environ.get("SUITE_N_BOOT", "1000")),
        }
    return _ambiente_cache


def pytest_report_header(config) -> list[str]:
    """Cabeçalho da sessão: SHA do SUT e versões pinadas (SPEC S4)."""
    amb = descrever_ambiente()
    versoes = " ".join(f"{p}={v}" for p, v in sorted(amb["versoes"].items()))
    return [
        f"SUT: {RAIZ_SUT} @ {amb['sha'] or '(sem repositório git)'}"
        f" (sentinela {amb['versao_sentinela']})",
        f"versões: {versoes}",
        f"SUITE_SEED={os.environ.get('SUITE_SEED', '42')}"
        f" SUITE_N_BOOT={os.environ.get('SUITE_N_BOOT', '1000')}",
    ]


# --- reprodutibilidade -----------------------------------------------------

@pytest.fixture(scope="session")
def ambiente() -> dict:
    return descrever_ambiente()


@pytest.fixture
def semente() -> int:
    return int(os.environ.get("SUITE_SEED", "42"))


@pytest.fixture
def gerador(semente):
    """Gerador NOVO por teste: um teste nunca herda o estado do anterior."""
    import numpy as np

    return np.random.default_rng(semente)


@pytest.fixture
def n_boot() -> int:
    return int(os.environ.get("SUITE_N_BOOT", "1000"))


# --- lotes -----------------------------------------------------------------
# Convenção de D3: `_lote_x` é de sessão e NUNCA é injetado num teste;
# `lote_x` é por função e devolve uma cópia, porque metade dos testes
# adversariais muta o quadro.

@pytest.fixture(scope="session")
def _lote_treino():
    return sn.dados.carregar("treino")


@pytest.fixture(scope="session")
def _lote_teste():
    return sn.dados.carregar("teste")


@pytest.fixture(scope="session")
def _lote_producao():
    return sn.dados.carregar("producao")


@pytest.fixture
def lote_treino(_lote_treino):
    return _lote_treino.copy()


@pytest.fixture
def lote_teste(_lote_teste):
    return _lote_teste.copy()


@pytest.fixture
def lote_producao(_lote_producao):
    return _lote_producao.copy()


@pytest.fixture(scope="session")
def predicoes(_lote_treino, _lote_teste, _lote_producao):
    """Uma única passagem de floresta por (conjunto, versão, limiar) — D6.

    Devolve uma função memoizada `(conjunto, versao, limiar) -> (y, proba,
    predicao)`. Sem isso, dezenas de testes reexecutariam a floresta sobre
    4.200 linhas.
    """
    lotes = {"treino": _lote_treino, "teste": _lote_teste, "producao": _lote_producao}
    cache: dict = {}

    def obter(conjunto: str, versao: str = "v1", limiar: float = modelo.LIMIAR_PADRAO):
        chave = (conjunto, versao, limiar)
        if chave not in cache:
            saida = pipeline.executar(lotes[conjunto], versao=versao, limiar=limiar)
            y = saida["falha_72h"].to_numpy() if "falha_72h" in saida.columns else None
            cache[chave] = (y, saida["probabilidade"].to_numpy(), saida["predicao"].to_numpy())
        return cache[chave]

    return obter


# --- isolamento do estado global (SPEC S12, D4) ----------------------------

@pytest.fixture(autouse=True)
def _isola_estado_global():
    """Zera `_RISCO_CONGELADO`; vigia `_CACHE`.

    Zerar o risco custa reler 466 bytes. Limpar `modelo._CACHE` custaria
    reparsear ~550 KB de JSON por teste, então ele é apenas vigiado: nenhum
    teste pode trocar por baixo do pano um modelo já carregado.
    """
    features._RISCO_CONGELADO = None
    antes = dict(modelo._CACHE)
    yield
    features._RISCO_CONGELADO = None
    for versao, objeto in antes.items():
        assert modelo._CACHE.get(versao) is objeto, (
            f"modelo._CACHE['{versao}'] foi substituído durante o teste; "
            "use a fixture `modelo_cache_frio` em vez de mexer no cache"
        )


@pytest.fixture
def modelo_cache_frio():
    """Cache vazio para o único teste que precisa observar a primeira carga."""
    anterior = dict(modelo._CACHE)
    modelo._CACHE.clear()
    yield modelo._CACHE
    modelo._CACHE.clear()
    modelo._CACHE.update(anterior)


# --- medições (SPEC C8) ----------------------------------------------------

@pytest.fixture
def medicoes() -> dict:
    """Dicionário onde os testes gravam o que mediram."""
    return _MEDICOES


def caminho_medicoes() -> pathlib.Path:
    return pathlib.Path(
        os.environ.get("SUITE_MEDICOES", "evidencias/medicoes.json")
    )


def _fundir(existente: dict, novo: dict) -> dict:
    """Funde o que ESTA sessão mediu sobre o que já havia no arquivo.

    Escrever `_MEDICOES` por cima do arquivo inteiro destruía chaves de outro produtor:
    `scripts/linha_de_base.py` grava `linha_de_base` (e `acuracia_sempre_zero` em
    `contrato_dados`), e qualquer `pytest` posterior zerava as duas — o `medicoes.json`
    entregue ficava sem a chave que SPEC C8 exige. Descoberto ao executar o HANDOFF 04.

    Regra: uma chave que esta sessão **não** preencheu (container vazio) preserva o que
    estava lá; uma que ela preencheu substitui. Dicionário funde por subchave, para que
    `-m unitario` não apague o que `-m estatistico` mediu.

    Continua determinístico, que é o que S13 cobra: a mesma sequência de comandos com a
    mesma semente produz o mesmo arquivo. Regeneração do zero é `make evidencias`.
    """
    saida = dict(existente)
    for chave, valor in novo.items():
        if isinstance(valor, dict) and isinstance(saida.get(chave), dict):
            fundido = dict(saida[chave])
            for sub, v in valor.items():
                if isinstance(v, dict) and isinstance(fundido.get(sub), dict):
                    fundido[sub] = {**fundido[sub], **v}
                else:
                    fundido[sub] = v
            saida[chave] = fundido
        elif valor or chave not in saida:
            saida[chave] = valor
    return saida


def pytest_sessionfinish(session, exitstatus) -> None:
    """Despeja `medicoes.json`. Sem relógio nem duração: mesma semente, mesmo
    arquivo, byte a byte (SPEC S13)."""
    _MEDICOES["sut"] = descrever_ambiente()
    destino = caminho_medicoes()
    destino.parent.mkdir(parents=True, exist_ok=True)

    anterior: dict = {}
    if destino.exists():
        try:
            anterior = json.loads(destino.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            anterior = {}        # arquivo corrompido: esta sessão reescreve do zero

    destino.write_text(
        json.dumps(_fundir(anterior, _MEDICOES), indent=2, sort_keys=True, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
