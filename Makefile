# Os doze alvos de SPEC C3. Cada alvo é um `docker compose run` — este
# Makefile é a única documentação de comando que o README precisa citar.
#
# Use ARGS para passar opções extras ao pytest:
#   make suite ARGS="--collect-only -q"

# O uid/gid REAIS deste host vão para o build. Sem isso, os arquivos de
# evidencias/ sairiam com dono errado (SPEC S7).
#
# São SUITE_UID/SUITE_GID e não UID/GID porque em bash `UID` é readonly e não
# exportada — pelo shell ela nunca chegaria ao compose. Assim os dois caminhos,
# `make build` e `docker compose build`, passam o mesmo uid.
export SUITE_UID := $(shell id -u)
export SUITE_GID := $(shell id -g)

COMPOSE := docker compose
ARGS ?=
EVID  := evidencias

.PHONY: build suite rapido unitario estatistico adversarial defeitos \
        correcoes evidencias colecao lento limpar garantir-evidencias

# Alvo interno: o diretório de evidências precisa existir ANTES de qualquer
# `run`, senão o Docker o criaria como root (SPEC S7).
garantir-evidencias:
	@mkdir -p $(EVID)

build:
	$(COMPOSE) build

# Suíte completa: o comando único de entrega (SPEC C1).
# O log é escrito DENTRO do container (não por um `tee` do host): é assim que
# `evidencias/log-suite.txt` sai com o uid do host e prova S7. `pipefail` faz o
# alvo herdar o exit code do pytest, não o do tee.
suite: garantir-evidencias
	$(COMPOSE) run --rm suite bash -o pipefail -c \
	  'pytest --junitxml=$(EVID)/junit-suite.xml $(ARGS) 2>&1 | tee $(EVID)/log-suite.txt'

# Exclui os testes marcados `lento` (SPEC S11: abaixo de 60 s).
rapido: garantir-evidencias
	$(COMPOSE) run --rm suite pytest -m "not lento" $(ARGS)

unitario: garantir-evidencias
	$(COMPOSE) run --rm suite pytest -m unitario $(ARGS)

estatistico: garantir-evidencias
	$(COMPOSE) run --rm suite pytest -m estatistico $(ARGS)

adversarial: garantir-evidencias
	$(COMPOSE) run --rm suite pytest -m adversarial $(ARGS)

# Sai 1 de propósito: é o log vermelho da entrega (SPEC S5). O `-` faz o make
# não abortar com esse 1 esperado; o exit code real fica no log.
defeitos: garantir-evidencias
	-$(COMPOSE) run --rm defeitos bash -o pipefail -c \
	  'pytest -m defeito --runxfail --junitxml=$(EVID)/junit-defeitos.xml $(ARGS) 2>&1 \
	   | tee $(EVID)/log-defeitos.txt'

correcoes: garantir-evidencias
	$(COMPOSE) run --rm correcoes

evidencias: garantir-evidencias
	$(COMPOSE) run --rm evidencias

colecao: garantir-evidencias
	$(COMPOSE) run --rm suite pytest --collect-only -q $(ARGS)

lento: garantir-evidencias
	$(COMPOSE) run --rm suite pytest -m lento $(ARGS)

# Remove caches e containers parados. NÃO apaga evidencias/: aqueles
# arquivos são entregáveis (SPEC C7).
limpar:
	$(COMPOSE) down --remove-orphans
	rm -rf .pytest_cache
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
