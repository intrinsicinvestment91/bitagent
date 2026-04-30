PKG_ID := $(shell yq e ".id" < manifest.yaml)
PKG_VERSION := $(shell yq e ".version" < manifest.yaml)

DENO := $(shell which deno || echo $(HOME)/.deno/bin/deno)

.DELETE_ON_ERROR:

all: $(PKG_ID).s9pk

$(PKG_ID).s9pk: manifest.yaml instructions.md icon.png LICENSE scripts/embassy.js image.tar
	@echo "Packing $(PKG_ID) v$(PKG_VERSION)..."
	start-sdk pack
	@echo "Done: $(PKG_ID).s9pk"

scripts/embassy.js: scripts/embassy.ts scripts/procedures/*.ts scripts/deps.ts
	@echo "Bundling TypeScript procedures..."
	$(DENO) run --allow-read --allow-write --allow-env --allow-net scripts/bundle.ts
	@echo "embassy.js written"

image.tar: Dockerfile docker_entrypoint.sh requirements.txt main.py start9_server.py agent_logic.py agent_wallet.py lnbits_client.py src
	@echo "Building Docker image start9/$(PKG_ID)/main:$(PKG_VERSION)..."
	docker build --builder default --platform linux/amd64 -t start9/$(PKG_ID)/main:$(PKG_VERSION) .
	docker save start9/$(PKG_ID)/main:$(PKG_VERSION) -o image.tar
	@echo "image.tar written ($(shell du -h image.tar | cut -f1))"

install: $(PKG_ID).s9pk
	@if [ ! -f ~/.embassy/config.yaml ]; then \
		echo "ERROR: Set \"host: http://greasy-moons.local\" in ~/.embassy/config.yaml first"; exit 1; fi
	start-cli package install $(PKG_ID).s9pk

verify: $(PKG_ID).s9pk
	start-sdk verify s9pk $(PKG_ID).s9pk

clean:
	rm -f $(PKG_ID).s9pk image.tar scripts/embassy.js

.PHONY: all install verify clean
