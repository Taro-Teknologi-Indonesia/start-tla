# TLA+ command-line helpers. Run `make help` for the list of targets.

TLA_JAR_URL ?= https://github.com/tlaplus/tlaplus/releases/download/v1.8.0/tla2tools.jar
JAR         := tools/tla2tools.jar
JAVA        ?= java
WORKERS     ?= auto
TLC_FLAGS   ?=
STATES_DIR  := states

# Usage: make check SPEC=Counter   (SPEC = module name without .tla, inside specs/)
SPEC ?= Counter
DIR  := specs
TLA  := $(DIR)/$(SPEC).tla
CFG  := $(DIR)/$(SPEC).cfg

TLA_CP := $(JAVA) -cp $(JAR)

# TLA-ID: the same specs written with Indonesian keywords (specs/Name.tlaid + specs/Name.cfgid)
TLAID     := TLA_JAR=$(abspath $(JAR)) python3 tlaid/tlaid.py
TLAID_SRC := $(DIR)/$(SPEC).tlaid

.DEFAULT_GOAL := help
.PHONY: help setup parse check tlc pcal simulate repl new clean distclean cek urai repl-id terjemah kamus baru impor

help: ## Show this help
	@awk 'BEGIN{FS=":.*## "} /^[a-zA-Z_-]+:.*## /{printf "  \033[36m%-10s\033[0m %s\n",$$1,$$2}' $(MAKEFILE_LIST)
	@echo "\nVariables: SPEC=<Module> (default: $(SPEC)), WORKERS=<n|auto>, TLC_FLAGS=<extra TLC options>"

setup: $(JAR) ## Check Java and download tla2tools.jar
	@$(JAVA) -version 2>&1 | head -1

$(JAR):
	@command -v $(JAVA) >/dev/null || { echo "Java 11+ is required (e.g. brew install --cask temurin)"; exit 1; }
	@mkdir -p $(dir $(JAR))
	curl -fL -o $(JAR) $(TLA_JAR_URL)

parse: $(JAR) ## Syntax/semantic check with SANY: make parse SPEC=Name
	$(TLA_CP) tla2sany.SANY $(TLA)

check tlc: $(JAR) ## Run the TLC model checker: make check SPEC=Name
	@mkdir -p $(STATES_DIR)
	$(TLA_CP) tlc2.TLC -workers $(WORKERS) $(TLC_FLAGS) -metadir $(STATES_DIR) -config $(CFG) $(TLA)

simulate: $(JAR) ## Random simulation (no exhaustive search): make simulate SPEC=Name
	@mkdir -p $(STATES_DIR)
	$(TLA_CP) tlc2.TLC -simulate -workers $(WORKERS) $(TLC_FLAGS) -metadir $(STATES_DIR) -config $(CFG) $(TLA)

pcal: $(JAR) ## Translate PlusCal to TLA+ in place: make pcal SPEC=Name
	$(TLA_CP) pcal.trans $(TLA)

repl: $(JAR) ## Interactive TLA+ REPL
	$(TLA_CP) tlc2.REPL

new: ## Scaffold a new spec: make new SPEC=Name
	@test ! -e $(TLA) || { echo "$(TLA) already exists"; exit 1; }
	@printf -- '---- MODULE $(SPEC) ----\nEXTENDS Naturals\n\nVARIABLE x\n\nInit == x = 0\nNext == x\x27 = x\n\nSpec == Init /\\ [][Next]_x\n\nTypeOK == x \\in Nat\n====\n' > $(TLA)
	@printf 'SPECIFICATION Spec\nINVARIANT TypeOK\n' > $(CFG)
	@echo "Created $(TLA) and $(CFG)"

cek: $(JAR) ## TLA-ID: model-check an Indonesian spec: make cek SPEC=Name
	$(TLAID) cek $(TLAID_SRC) -workers $(WORKERS) $(TLC_FLAGS)

urai: $(JAR) ## TLA-ID: parse an Indonesian spec with SANY: make urai SPEC=Name
	$(TLAID) urai $(TLAID_SRC)

repl-id: $(JAR) ## TLA-ID: REPL that reads and answers in TLA-ID
	@$(TLAID) repl

terjemah: ## TLA-ID: translate one expression to TLA+: make terjemah E='{1} GABUNG {2}'
	@test -n "$$E" || { echo "Usage: make terjemah E='{1} GABUNG {2}'"; exit 2; }
	@$(TLAID) tla -e "$$E"

kamus: ## TLA-ID: table of TLA-ID and TLA+ constructs side by side
	@$(TLAID) kamus

baru: ## TLA-ID: start a new Indonesian spec: make baru SPEC=Name
	@$(TLAID) baru $(DIR)/$(SPEC)

impor: ## TLA-ID: convert specs/Name.tla and .cfg to .tlaid and .cfgid
	@test ! -e $(TLAID_SRC) || { echo "$(TLAID_SRC) already exists"; exit 1; }
	$(TLAID) impor $(TLA) > $(TLAID_SRC)
	@test ! -e $(CFG) || $(TLAID) impor $(CFG) > $(DIR)/$(SPEC).cfgid

clean: ## Remove TLC state dirs and generated files
	rm -rf $(STATES_DIR) $(DIR)/*.old $(DIR)/*.pdf $(DIR)/*.dvi $(DIR)/*.log $(DIR)/*_TTrace_* $(DIR)/.tlaid-out

distclean: clean ## Also remove the downloaded tla2tools.jar
	rm -rf tools
