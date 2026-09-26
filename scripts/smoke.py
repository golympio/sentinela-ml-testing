"""Smoke de integridade do SUT — último passo do build e fonte única do D23.

Roda dentro da imagem, logo depois de instalar o pacote sob teste. Confere o que
`verificar_manifest()` devolve contra a lista de divergências **catalogadas**, e aborta
o build se aparecer qualquer divergência fora dela — ou se uma das catalogadas sumir,
que é o sinal de que o SUT mudou por baixo do SHA pinado.

`DIVERGENCIAS_CONHECIDAS` é importado também por `tests/test_reprodutibilidade.py`,
para que o defeito seja descrito em um lugar só.
"""
from __future__ import annotations

import sys

# D23 — o manifest do SUT está desatualizado no commit pinado
# c9020d7ba3bb4e6fd4ae22d46346a787b16adc02: os três CSVs de `dados/` e a tabela
# `risco_maquina.json` foram regerados sem que `manifest.json` fosse reescrito. Os dois
# artefatos de modelo, esses sim, batem. Verificado em clone limpo
# (`git status --porcelain` vazio), portanto é defeito do SUT, não do nosso ambiente.
# O README do próprio SUT documenta `[]` como contrato, o que confirma a intenção violada.
DIVERGENCIAS_CONHECIDAS = frozenset(
    {
        "sha256 diferente: dados/treino.csv",
        "sha256 diferente: dados/teste.csv",
        "sha256 diferente: dados/producao.csv",
        "sha256 diferente: artefatos/risco_maquina.json",
    }
)

VERSAO_ESPERADA = "1.0.0"
N_FEATURES_ESPERADO = 13


def main() -> int:
    import sentinela as sn

    versao = sn.__version__
    n_features = len(sn.features.ORDEM_FEATURES)
    problemas = set(sn.artefatos.verificar_manifest())

    inesperadas = sorted(problemas - DIVERGENCIAS_CONHECIDAS)
    sumidas = sorted(DIVERGENCIAS_CONHECIDAS - problemas)

    erros: list[str] = []
    if versao != VERSAO_ESPERADA:
        erros.append(f"versão do SUT: esperada {VERSAO_ESPERADA}, obtida {versao}")
    if n_features != N_FEATURES_ESPERADO:
        erros.append(f"nº de features: esperado {N_FEATURES_ESPERADO}, obtido {n_features}")
    if inesperadas:
        erros.append("divergência de manifest não catalogada: " + ", ".join(inesperadas))
    if sumidas:
        erros.append(
            "divergência de D23 desapareceu (o SUT mudou sob o SHA pinado?): "
            + ", ".join(sumidas)
        )

    if erros:
        print("smoke FALHOU:", file=sys.stderr)
        for erro in erros:
            print(f"  - {erro}", file=sys.stderr)
        return 1

    print(
        f"smoke ok: {versao} | features: {n_features} | "
        f"manifest: D23 ({len(DIVERGENCIAS_CONHECIDAS)} divergências conhecidas, 0 inesperadas)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
