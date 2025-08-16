SHELL := bash
.DEFAULT_GOAL := help

RUFF := uvx -q ruff
BASEDPYRIGHT := uvx -q basedpyright

# Directories/files to check
PY_DIRS := src

.PHONY: help fmt format lint lint-fix check typecheck

help:
	@echo "Available targets:"
	@echo "  fmt        Format code with Ruff formatter"
	@echo "  lint       Lint with Ruff (no changes)"
	@echo "  lint-fix   Lint and auto-fix issues"
	@echo "  check      Run formatter in check mode and linter"
	@echo "  typecheck  Run basedpyright type checker"

fmt:
	$(RUFF) format $(PY_DIRS)

# Alias
format: fmt

lint:
	$(RUFF) check $(PY_DIRS)

lint-fix:
	$(RUFF) check --fix $(PY_DIRS)

check:
	$(RUFF) format --check $(PY_DIRS)
	$(RUFF) check $(PY_DIRS)

typecheck:
	$(BASEDPYRIGHT) .
