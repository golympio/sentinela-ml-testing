# Ambiente reprodutível da suíte de testes do Sentinela.
#
# O sistema sob teste (SUT) NÃO vive neste repositório: ele é clonado aqui, no
# commit pinado por SENTINELA_REF, e instalado em modo editável — obrigatório,
# porque `artefatos.RAIZ` é `parents[2]` do módulo e uma instalação normal
# quebraria a localização de `dados/` e `artefatos/` (SPEC P2 / D12).
FROM python:3.12-slim

# uid/gid do usuário do container, que precisa bater com o do seu usuário no
# host: `evidencias/` é um bind mount, e uid diferente faz a suíte falhar ao
# escrever lá (SPEC S7).
#
# O nome é SUITE_UID, e não UID, de propósito: em bash `UID` é uma variável
# especial, READONLY e NÃO EXPORTADA, então `UID=... docker compose build` é
# silenciosamente ignorado e o build cai no default. Com SUITE_UID a forma
# `SUITE_UID=$(id -u) docker compose build` funciona em qualquer shell.
ARG SUITE_UID=1001
ARG SUITE_GID=1001

# Origem e versão do SUT. SENTINELA_REPO aceita um espelho local para o caso
# de build sem rede (SPEC S2).
ARG SENTINELA_REPO=https://github.com/felipehp/sentinela-nortemec
ARG SENTINELA_REF=c9020d7ba3bb4e6fd4ae22d46346a787b16adc02

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_ROOT_USER_ACTION=ignore

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates git \
 && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid "${SUITE_GID}" suite \
 && useradd --uid "${SUITE_UID}" --gid "${SUITE_GID}" --create-home --shell /bin/bash suite

# Dependências pinadas antes do clone: mudam pouco e cacheiam bem.
COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

# --- layer isolada: clone do SUT e verificação do SHA ----------------------
# `git clone` completo + `checkout --detach` (D11): há servidores que recusam
# buscar um SHA solto, e o repositório tem ~2,4 MB.
RUN set -u; \
    if ! git clone "${SENTINELA_REPO}" /opt/sentinela; then \
        echo "ERRO: o clone do SUT falhou; build abortado." >&2; \
        echo "  SENTINELA_REPO: ${SENTINELA_REPO}" >&2; \
        echo "  Sem rede ou repositório inacessível? Aponte SENTINELA_REPO para um" >&2; \
        echo "  espelho local, ou use a imagem exportada com 'docker save' (SPEC S2)." >&2; \
        exit 1; \
    fi; \
    if ! git -C /opt/sentinela checkout --detach "${SENTINELA_REF}" 2>/tmp/checkout.err; then \
        echo "AVISO: checkout de ${SENTINELA_REF} falhou:" >&2; \
        sed 's/^/  /' /tmp/checkout.err >&2; \
    fi; \
    obtido="$(git -C /opt/sentinela rev-parse HEAD)"; \
    if [ "${obtido}" != "${SENTINELA_REF}" ]; then \
        echo "ERRO: o SUT nao esta no commit pinado; build abortado." >&2; \
        echo "  SENTINELA_REF esperado: ${SENTINELA_REF}" >&2; \
        echo "  git rev-parse HEAD:     ${obtido}" >&2; \
        exit 1; \
    fi; \
    echo "SUT verificado no commit ${obtido}"

# `-e` é exigido por P2; `--no-deps` impede que os `>=` do SUT subam as
# versões pinadas em requirements.txt (NF3 / D12).
RUN pip install --no-deps -e /opt/sentinela \
 && chown -R "${SUITE_UID}:${SUITE_GID}" /opt/sentinela

# SENTINELA_REF precisa sobreviver ao build: a suíte compara o SHA do clone
# com ele em tempo de execução (tests/test_reprodutibilidade.py).
ENV SENTINELA_REF=${SENTINELA_REF} \
    SENTINELA_REPO=${SENTINELA_REPO}

WORKDIR /trabalho
USER suite
CMD ["pytest"]

# Último passo do build: o smoke.
#
# O manifest do SUT está desatualizado no commit pinado — quatro divergências
# reais de sha256, catalogadas como D23 em `scripts/smoke.py`. O smoke tolera
# exatamente essas quatro e ABORTA o build diante de qualquer outra, ou caso
# uma delas desapareça (sinal de que o SUT mudou sob o SHA). Nada aqui altera
# o SUT: só o observamos (SPEC C12).
COPY scripts/smoke.py /usr/local/lib/smoke.py
RUN python /usr/local/lib/smoke.py
