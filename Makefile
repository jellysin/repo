# Repository-owned verification. `make verify-all` is the local gate.
# Governance targets run the engine that PRAETOR_REF pins, resolved by engine.mk.
-include .config/praetor/engine.mk
PYTHON := python3
ACTIONLINT := actionlint
# release-helper at the one commit the workflows pin; scripts/release_helper.py fetches it once.
HELPER := $(PYTHON) -B scripts/release_helper.py
.PHONY: verify-all interpreter compile-context compile-context-verify caveman-sources audit policy catalog manifest test workflows server-check

# One step at a time, in the listed order, also under make -j: no check starts before the interpreter check.
.NOTPARALLEL:

verify-all: interpreter compile-context-verify caveman-sources audit policy catalog manifest test workflows

# The interpreter must come from the minor line .python-version pins; the other targets run on it.
interpreter:
	@$(PYTHON) -B scripts/python_pin.py

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

# Published versions stay as main has them, and every listed version can be downloaded.
manifest:
	@$(PYTHON) -B scripts/manifest_checks.py history origin/main
	@$(PYTHON) -B scripts/manifest_checks.py releases

test:
	@$(PYTHON) -B -m unittest discover -s tests

workflows:
	@$(ACTIONLINT)

# Needs Docker and pulls the Jellyfin server image; CI runs it in the job server-check.
server-check:
	@$(HELPER) server-check --manifest manifest.json
