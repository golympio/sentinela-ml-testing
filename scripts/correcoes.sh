#!/usr/bin/env bash
# Aplica os patches de patches/*.patch ao clone do SUT DENTRO do container e mede o efeito.
#
# Roda pelo serviço `correcoes` do compose (`command: ["bash","scripts/correcoes.sh"]`,
# working_dir `/trabalho`). Fora do container não funciona — o SUT vive em `/opt/sentinela`.
#
# O container é descartado ao fim (`--rm`), então a alteração no clone **não sobrevive** e o nosso
# repositório nunca contém o pacote sob teste (C12/V11). Nada aqui toca o host.
#
# `python -m` / `python -` em vez de `python arquivo.py`: ver `docs/decisoes.md`,
# "`scripts/linha_de_base.py` só roda como módulo".
set -uo pipefail

SUT="${SUT:-/opt/sentinela}"
PATCHES="${PATCHES:-/trabalho/patches}"

# CRÍTICO: todo pytest deste script roda com os patches APLICADOS, e o
# `pytest_sessionfinish` do conftest grava em `SUITE_MEDICOES`. Sem redirecionar, as medições do
# sistema **corrigido** sobrescreveriam as do sistema **como ele é** em
# `evidencias/medicoes.json`, que é a fonte de todo número do relatório. Descoberto na execução
# do HANDOFF 06: o arquivo mudou de 22.721 para 22.659 bytes depois da primeira passada.
export SUITE_MEDICOES=/tmp/medicoes-correcoes.json

echo "=== correcoes.sh — aplica os patches e mede o antes/depois ==="
echo "SUT=${SUT}  PATCHES=${PATCHES}"
echo

# ------------------------------------------------------- 0. o clone tem de estar limpo
if [ -n "$(git -C "$SUT" status --porcelain)" ]; then
  echo "ERRO: o clone do SUT já está sujo antes de começar. Abortando." >&2
  git -C "$SUT" status --porcelain >&2
  exit 1
fi

ARQUIVOS=$(ls "${PATCHES}"/*.patch 2>/dev/null)
if [ -z "$ARQUIVOS" ]; then
  echo "ERRO: nenhum .patch em ${PATCHES}." >&2
  exit 1
fi

# ------------------------------------------------------- 1. métricas ANTES
echo "--- [1/5] métricas ANTES (SUT no commit pinado, com os defeitos presentes)"
python - <<'PY' > /tmp/antes.json
import json
import sentinela as sn
from suite import harness, metricas
import numpy as np
saida = {}
for versao in ("v1", "v2"):
    y, proba, pred = harness.prever_sem_vazamento(
        sn.preprocessamento.limpar(sn.dados.carregar("teste")), versao)
    vp = int(((pred == 1) & (y == 1)).sum()); fp = int(((pred == 1) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())
    saida[versao] = {
        "recall": vp / (vp + fn) if vp + fn else 0.0,
        "precisao": vp / (vp + fp) if vp + fp else 0.0,
        "f2": metricas.fbeta(y, pred, beta=2.0),
        "pr_auc": metricas.average_precision(y, proba),
        "custo": 20 * fn + fp,
        "linhas": int(len(y)),
    }
print(json.dumps(saida))
PY
if [ ! -s /tmp/antes.json ]; then
  echo "ERRO: não consegui medir o estado ANTES. Abortando antes de aplicar qualquer patch." >&2
  exit 1
fi
echo "ok"
echo

# ------------------------------------------------------- 2. aplicar, um a um
echo "--- [2/5] aplicando os patches"
N=0
for patch in $ARQUIVOS; do
  nome=$(basename "$patch")
  if ! git -C "$SUT" apply "$patch"; then
    echo "ERRO: o patch '${nome}' NÃO aplicou. Revertendo os ${N} já aplicados e abortando." >&2
    git -C "$SUT" checkout -- . 2>/dev/null || true
    exit 1
  fi
  N=$((N + 1))
  echo "  aplicado: ${nome}"
done
echo "${N} patches aplicados"
echo

# --------------------------------------- 3. o manifest NÃO pode ter mudado (D23, não [])
echo "--- [3/5] o manifest continua nas 4 divergências de D23?"
python - <<'PY'
import sys
import sentinela as sn
from scripts.smoke import DIVERGENCIAS_CONHECIDAS
atual = set(sn.artefatos.verificar_manifest())
esperado = set(DIVERGENCIAS_CONHECIDAS)
# Os patches mexem em src/, e o manifest cobre dados/ e artefatos/ — nada pode ter mudado.
# O contrato NÃO é `== []`: desde o HANDOFF 01 o SUT vem de fábrica com 4 divergências (D23).
if atual != esperado:
    print(f"ERRO: o manifest mudou. a mais: {sorted(atual - esperado)} | "
          f"a menos: {sorted(esperado - atual)}", file=sys.stderr)
    sys.exit(1)
print(f"  ok: exatamente as {len(atual)} divergências catalogadas em D23, nenhuma a mais")
PY
MANIFEST_OK=$?
echo

# ------------------------------------------------------- 4. re-rodar os testes de defeito
echo "--- [4/5] re-rodando -m defeito com os patches aplicados"
pytest -m defeito --runxfail -q 2>&1 | tail -15
echo
echo "    Os testes de D01, D02, D03 e D19, nominalmente:"
for t in \
  "tests/test_features.py::test_temp_media_6h_nao_muda_quando_so_o_futuro_muda" \
  "tests/test_vazamento_alvo.py::test_maquina_risco_nao_depende_do_rotulo_do_proprio_lote" \
  "tests/test_preprocessamento.py::test_limpar_converte_pressao_de_psi_para_bar" \
  "tests/test_preprocessamento.py::test_limpar_rejeita_unidade_de_pressao_desconhecida" ; do
  if pytest --runxfail -q "$t" > /dev/null 2>&1; then
    printf '      PASSA  %s\n' "$(basename "$t")"
  else
    printf '      falha  %s\n' "$(basename "$t")"
  fi
done
echo

# ------------------------------------------------------- 5. métricas DEPOIS + tabela
echo "--- [5/5] métricas DEPOIS, e a tabela antes/depois"
python - <<'PY'
import json
import sentinela as sn
from suite import harness, metricas

antes = json.load(open("/tmp/antes.json"))
depois = {}
for versao in ("v1", "v2"):
    y, proba, pred = harness.prever_sem_vazamento(
        sn.preprocessamento.limpar(sn.dados.carregar("teste")), versao)
    vp = int(((pred == 1) & (y == 1)).sum()); fp = int(((pred == 1) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())
    depois[versao] = {
        "recall": vp / (vp + fn) if vp + fn else 0.0,
        "precisao": vp / (vp + fp) if vp + fp else 0.0,
        "f2": metricas.fbeta(y, pred, beta=2.0),
        "pr_auc": metricas.average_precision(y, proba),
        "custo": 20 * fn + fp,
        "linhas": int(len(y)),
    }

print()
print("  conjunto TESTE, sem vazamento, limiar 0,5 — custo = 20*FN + FP")
print()
cab = f"  {'versão':7} {'métrica':10} {'antes':>12} {'depois':>12} {'Δ (depois−antes)':>18}"
print(cab); print("  " + "-" * (len(cab) - 2))
for versao in ("v1", "v2"):
    for m in ("recall", "precisao", "f2", "pr_auc", "custo", "linhas"):
        a, d = antes[versao][m], depois[versao][m]
        if isinstance(a, int):
            print(f"  {versao:7} {m:10} {a:12d} {d:12d} {d - a:+18d}")
        else:
            print(f"  {versao:7} {m:10} {a:12.6f} {d:12.6f} {d - a:+18.6f}")
    print()

piorou = [v for v in ("v1", "v2") if depois[v]["custo"] > antes[v]["custo"]]
print("  LEITURA")
if piorou:
    print(f"  O custo PIOROU em: {', '.join(piorou)}. **Isso é o achado, não um bug da correção.**")
else:
    print("  O custo não piorou — resultado inesperado, vale investigar antes de afirmar qualquer coisa.")
print("  Os artefatos de modelo foram treinados COM os defeitos presentes: a floresta aprendeu a")
print("  usar `maquina_risco` inflada pelo rótulo e a pressão em duas escalas misturadas. Corrigir")
print("  a entrada sem retreinar entrega ao modelo uma distribuição que ele nunca viu.")
print()
print("  Corrigir o código exige retreinar. E retreinar exige, antes, esta suíte — porque sem ela")
print("  não há como saber se o modelo novo é melhor que o velho.")
PY
echo

# ------------------------------------------------------- limpeza
echo "--- revertendo o clone (o container é descartado de qualquer forma)"
git -C "$SUT" checkout -- .
if [ -n "$(git -C "$SUT" status --porcelain)" ]; then
  echo "AVISO: o clone não voltou ao estado limpo." >&2
else
  echo "clone limpo: o pacote sob teste não foi alterado de forma persistente (C12/V11)"
fi

echo
if [ "$MANIFEST_OK" -eq 0 ]; then
  echo "=== correcoes.sh: OK — ${N} patches aplicados ==="
  exit 0
fi
echo "=== correcoes.sh: o manifest divergiu do catalogado ==="
exit 1
