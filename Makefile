# Repository-owned verification. `make verify-all` is the local gate.
# Governance targets run the engine that PRAETOR_REF pins, resolved by engine.mk.
-include .config/praetor/engine.mk
PYTHON := python3
ACTIONLINT := actionlint
# release-helper at the one commit the workflows pin; scripts/release_helper.py fetches it once.
HELPER := $(PYTHON) -B scripts/release_helper.py
.PHONY: verify-all compile-context compile-context-verify caveman-sources audit policy catalog test workflows server-check

verify-all: compile-context-verify caveman-sources audit policy catalog test workflows

compile-context:
	@$(PRAETORCTL) compile-context

compile-context-verify:
	@$(PRAETORCTL) compile-context --verify

caveman-sources:
	@$(PRAETORCTL) caveman check --configured-sources

audit:
	@$(PRAETORCTL) audit

policy:
	@$(HELPER) check-policy

catalog:
	@$(HELPER) validate-catalog

test:
	@$(PYTHON) -B -m unittest discover -s tests

workflows:
	@$(ACTIONLINT)

# Needs Docker and pulls the Jellyfin server image; CI runs it in the job server-check.
server-check:
	@$(HELPER) server-check --manifest manifest.json
