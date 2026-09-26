#!/usr/bin/env bash
# Gera os sete artefatos de saída de SPEC C7, em `evidencias/`.
#
# Roda DENTRO do container, pelo serviço `evidencias` do compose
# (`command: ["bash","scripts/evidencias.sh"]`, working_dir `/trabalho`, `SUITE_N_BOOT=2000`).
# Fora do container ele não funciona — o SUT vive em `/opt/sentinela`.
#
# Três restrições que `docs/decisoes.md` registrou e que este script existe para respeitar:
#
#  1. `python -m scripts.linha_de_base`, NUNCA `python scripts/linha_de_base.py`. Pelo caminho
#     do arquivo o `sys.path[0]` vira `scripts/` e `suite/` deixa de ser visto:
#     `ModuleNotFoundError: No module named 'suite'`. Com `-m`, quem entra no path é `/trabalho`.
#
#  2. A ORDEM importa. `medicoes.json` tem dois produtores — este script (chave `linha_de_base`)
#     e o `pytest_sessionfinish` do `conftest.py` (todas as outras). O `conftest._fundir`
#     preserva a chave que a sessão não preencheu, então a linha de base sobrevive ao pytest que
#     vem depois. O inverso não é verdade em espírito: gerar a linha de base DEPOIS reescreveria
#     o arquivo sem as chaves da suíte.
#
#  3. Regenerar do zero APAGA o arquivo antes. A fusão protege contra apagamento cruzado, não
#     contra dado velho: um produtor que deixe de rodar teria seu valor obsoleto preservado em
#     silêncio, e ninguém veria.
#
# `set -e` está deliberadamente FORA: o passo dos defeitos **deve** sair 1 (SPEC S5, é o log
# vermelho da entrega) e abortar ali seria abortar no sucesso.
set -uo pipefail

EVID="${EVID:-evidencias}"
MED="${SUITE_MEDICOES:-/trabalho/${EVID}/medicoes.json}"
FALHAS=0

echo "=== evidencias.sh — SPEC C7 ==="
echo "SUITE_SEED=${SUITE_SEED:-42}  SUITE_N_BOOT=${SUITE_N_BOOT:-1000}  MEDICOES=${MED}"
echo

mkdir -p "$EVID"

# ---------------------------------------------------------------- 1. do zero
echo "--- [1/5] apagando medicoes.json para regenerar do zero"
rm -f "$MED"

# ------------------------------------------------- 2. linha de base (1º produtor)
echo "--- [2/5] linha de base (python -m scripts.linha_de_base)"
if ! python -m scripts.linha_de_base; then
  echo "ERRO: a linha de base falhou; sem ela o relatório não tem de onde tirar número." >&2
  exit 1
fi
echo

# ------------------------------------- 3. suíte completa: DEVE sair 0 (C1, V2)
# Sem `-m`: a rodada completa inclui os testes `lento`, e é o que preenche
# `sensibilidade` e `estabilidade`. Rodar só `-m rapido` deixaria as duas obsoletas.
echo "--- [3/5] suíte completa (deve sair 0)"
pytest --junitxml="${EVID}/junit-suite.xml" 2>&1 | tee "${EVID}/log-suite.txt"
SAIDA_SUITE=${PIPESTATUS[0]}
echo "exit=${SAIDA_SUITE}" | tee -a "${EVID}/log-suite.txt"
if [ "$SAIDA_SUITE" -ne 0 ]; then
  echo "ERRO: a suíte não saiu 0 (saiu ${SAIDA_SUITE}). C1/V2 exigem verde." >&2
  FALHAS=$((FALHAS + 1))
fi
echo

# ------------------------------------ 4. só os defeitos: DEVE sair 1 (S5, V4)
echo "--- [4/5] defeitos com --runxfail (deve sair 1)"
pytest -m defeito --runxfail --junitxml="${EVID}/junit-defeitos.xml" 2>&1 \
  | tee "${EVID}/log-defeitos.txt"
SAIDA_DEF=${PIPESTATUS[0]}
echo "exit=${SAIDA_DEF}" | tee -a "${EVID}/log-defeitos.txt"
if [ "$SAIDA_DEF" -ne 1 ]; then
  echo "ERRO: os defeitos saíram ${SAIDA_DEF}, e S5/V4 exigem 1." >&2
  echo "      exit 0 aqui significaria que nenhum defeito falha mais — xfail obsoleto." >&2
  FALHAS=$((FALHAS + 1))
fi
echo

# ----------------------------------------------- 5. correções (só com patches)
echo "--- [5/5] correções"
if compgen -G "patches/*.patch" > /dev/null; then
  bash scripts/correcoes.sh 2>&1 | tee "${EVID}/log-correcoes.txt"
  echo "exit=${PIPESTATUS[0]}" | tee -a "${EVID}/log-correcoes.txt"
else
  echo "patches/ ainda não tem .patch — log-correcoes.txt não é gerado nesta passada."
  echo "Os patches são a Etapa 1 do HANDOFF 06 e o guia do aluno os trata como OPCIONAIS;"
  echo "os outros seis artefatos de C7 não dependem deles. Rode este script de novo depois."
fi
echo

# ------------------------------------------------------------- conferência
echo "=== conferência dos artefatos de C7 ==="
OBRIGATORIOS="log-suite.txt log-defeitos.txt junit-suite.xml junit-defeitos.xml linha-de-base.md medicoes.json"
for f in $OBRIGATORIOS; do
  if [ -s "${EVID}/${f}" ]; then
    printf '  ok      %-22s %s bytes\n' "$f" "$(stat -c '%s' "${EVID}/${f}")"
  else
    printf '  FALTA   %-22s\n' "$f"
    FALHAS=$((FALHAS + 1))
  fi
done
if [ -s "${EVID}/log-correcoes.txt" ]; then
  printf '  ok      %-22s %s bytes\n' "log-correcoes.txt" "$(stat -c '%s' "${EVID}/log-correcoes.txt")"
else
  printf '  pendente %-21s (Etapa 1/2 do HANDOFF 06)\n' "log-correcoes.txt"
fi

# As onze chaves do esquema de C8. Se `sensibilidade` ou `estabilidade` vierem vazias, o
# passo [3] rodou sem os testes `lento` e o relatório citaria número velho.
echo
echo "=== chaves de medicoes.json (SPEC C8) ==="
python - "$MED" <<'PY'
import json, sys
esperadas = ["sut", "contrato_dados", "linha_de_base", "v1_v2", "limiar", "flip",
             "contrafactual", "drift", "sensibilidade", "estabilidade", "calibracao"]
d = json.load(open(sys.argv[1], encoding="utf-8"))
falta = [k for k in esperadas if k not in d or not d[k]]
for k in esperadas:
    v = d.get(k)
    print(f"  {'ok   ' if v else 'VAZIA'} {k:16} {len(v) if hasattr(v, '__len__') else v}")
sys.exit(1 if falta else 0)
PY
FALHAS=$((FALHAS + $?))

echo
if [ "$FALHAS" -eq 0 ]; then
  echo "=== evidencias.sh: OK ==="
  exit 0
fi
echo "=== evidencias.sh: ${FALHAS} problema(s) — ver acima ==="
exit 1
