
.PHONY: format format-check
format:
	python3 scripts/format.py
format-check:
	python3 scripts/format.py --check

ZOMBIE_CORE_DIR ?= $(shell python3 scripts/dependencies.py path gateway-core)
ZOMBIE_RUNTIME_ROOT ?= $(CURDIR)
ZOMBIE_FULL_DIR := $(CURDIR)
export ZOMBIE_CORE_DIR ZOMBIE_RUNTIME_ROOT ZOMBIE_FULL_DIR
COMPOSE = docker compose --env-file $(ZOMBIE_RUNTIME_ROOT)/.local/gateway/compose.env -f compose.yaml
.PHONY: deps deps-check setup sources check build up down
deps:
	python3 scripts/dependencies.py fetch gateway-core
deps-check:
	python3 scripts/dependencies.py check gateway-core
setup:
	bash scripts/setup-runtime.sh
	python3 scripts/setup-youtube.py
	python3 scripts/setup-services.py
	python3 $(ZOMBIE_CORE_DIR)/scripts/generate-probes.py --output $(ZOMBIE_RUNTIME_ROOT)/.local/gateway/probes
	python3 $(ZOMBIE_CORE_DIR)/scripts/generate-extended-probes.py --output $(ZOMBIE_RUNTIME_ROOT)/.local/gateway/probes
sources: setup
	python3 scripts/setup-services.py --sources
check: setup
	bash -n install.sh control.sh bootstrap/launch-gateway.sh scripts/build-bootstrap.sh
	sh -n install-docker.sh scripts/fetch-alpine-sources.sh
	node --test bootstrap/configure-provider.test.mjs bootstrap/configure-spotify-mode.test.mjs bootstrap/configure-youtube-dial.test.mjs
	python3 -m unittest discover -s tests
	$(COMPOSE) --profile youtube --profile youtube-pot --profile youtube-receiver --profile spotify --profile airplay --profile threadfin --profile rebrowser config --quiet
build: setup
	$(COMPOSE) build gateway
up: deps
	$(MAKE) setup
	$(COMPOSE) build gateway
	$(COMPOSE) up -d
down:
	$(COMPOSE) down

.PHONY: tracks-smoke
tracks-smoke:
	python3 scripts/smoke-tracks.py

.PHONY: remote-smoke
remote-smoke:
	bash scripts/smoke-remote.sh

.PHONY: bootstrap-image
bootstrap-image:
	bash scripts/build-bootstrap.sh

.PHONY: soloist-config-check soloist-host-check soloist-runtime-check
soloist-config-check:
	ZOMBIE_RELAY_ADMIN_TOKEN=synthetic-test-token-012345678901234567890 docker compose -f compose.yaml -f compose.soloist.yaml --profile spotify --profile soloist config --quiet
soloist-host-check:
	python3 scripts/check-soloist-packaging.py
	$(MAKE) soloist-config-check
	$(MAKE) -C $(ZOMBIE_CORE_DIR) soloist-check
soloist-runtime-check:
	python3 scripts/check-soloist-runtime.py
