SHELL := /bin/bash
.DEFAULT_GOAL := help

ifeq ($(QTILE_CI_PYTHON),)
UV_PYTHON_ARG =
else
UV_PYTHON_ARG = --python=$(QTILE_CI_PYTHON)
endif

ifeq ($(QTILE_CI_BACKEND),)
PYTEST_BACKEND_ARG =
else
PYTEST_BACKEND_ARG = --backend=$(QTILE_CI_BACKEND)
endif

TEST_RUNNER = python3 -m pytest
ifeq ($(GITHUB_ACTIONS),true)
TEST_RUNNER = coverage run -m pytest
endif

# Optionally run the test suite under valgrind to surface leaks coming from
# the C extension (notably the wayland qw backend). Valgrind slows tests
# down by 10-50x, so this is opt-in via QTILE_CI_VALGRIND=1.
ifeq ($(QTILE_CI_VALGRIND),1)
VALGRIND_LOG_DIR = valgrind-logs
VALGRIND_CMD = valgrind \
	--tool=memcheck \
	--leak-check=full \
	--show-leak-kinds=definite,possible \
	--errors-for-leak-kinds=definite \
	--track-origins=yes \
	--trace-children=yes \
	--child-silent-after-fork=no \
	--num-callers=40 \
	--suppressions=$(PWD)/test/valgrind.supp \
	--log-file=$(VALGRIND_LOG_DIR)/valgrind.%p.log
# Bypass coverage's tracer under valgrind: it adds noise and is irrelevant
# for leak-finding.
TEST_RUNNER := $(VALGRIND_CMD) python3 -m pytest
# Tell CPython to use the system malloc so valgrind can track allocations
# and PyMalloc's arenas don't show up as one giant block.
export PYTHONMALLOC = malloc
endif

.PHONY: help
help: ## Show this help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "\033[1m%-15s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

.PHONY: deps
deps: ## Install all of qtile's dependencies.
	uv sync $(UV_PYTHON_ARG) --all-extras

.PHONY: check
check: deps ## Run the test suite on the latest python
	uv run ./libqtile/backend/wayland/cffi/build.py --debug
	if [ "$(QTILE_CI_VALGRIND)" = "1" ]; then \
		mkdir -p $(VALGRIND_LOG_DIR); \
	fi
	uv run $(UV_PYTHON_ARG) $(TEST_RUNNER) $(PYTEST_BACKEND_ARG); \
	TEST_RESULT=$$?; \
	if [ "$$GITHUB_ACTIONS" = "true" ]; then \
		echo "=== Backtraces ==="; \
		for corefile in coredumps/core*; do \
			[ -f "$$corefile" ] && gdb -batch -ex "bt full" -c "$$corefile"; \
		done; \
	fi; \
	if [ "$(QTILE_CI_VALGRIND)" = "1" ]; then \
		$(MAKE) valgrind-report; \
		TEST_RESULT=$$?; \
	fi; \
	if [ $$TEST_RESULT -ne 0 ]; then exit $$TEST_RESULT; fi
	if [ "$(QTILE_CI_VALGRIND)" != "1" ]; then \
		uv run coverage combine -q && \
		uv run coverage report -m && \
		uv run coverage xml; \
		if [ "$$GITHUB_ACTIONS" = "true" ]; then \
			uv tool run coveralls --service=github || true; \
		fi; \
	fi

.PHONY: valgrind-report
valgrind-report: ## Summarise valgrind logs and fail if definite leaks were found
	@echo "=== Valgrind summary ==="
	@scripts/valgrind-summary $(VALGRIND_LOG_DIR)

TTY := $(shell [ -t 0 ] && echo "-t")
DOCKER_RUN = docker run --rm -i $(TTY) \
	-v $(PWD):/workspace:z \
	-e USER_UID=$$(id -u) \
	-e USER_GID=$$(id -g) \
	-e HOME=/workspace \
	--env-file <(env) \
	qtile-ci

.PHONY: ci-check
ci-check: ## Run the test suite in the docker ci container
	$(DOCKER_RUN) make check

.PHONY: ci-bash
ci-bash: ## Run the test suite in the docker ci container
	$(DOCKER_RUN) bash

.PHONY: docs
docs: deps ## Run the sphinx build for the html docs.
	uv run $(MAKE) -C docs html

.PHONY: check-packaging
check-packaging:  ## Check that the packaging is sane
	uv run $(UV_PYTHON_ARG) check-manifest
	uv run $(UV_PYTHON_ARG) python3 -m build --sdist .
	uv run $(UV_PYTHON_ARG) twine check dist/*

.PHONY: lint
lint: ## Check the source code
	pre-commit run -a

.PHONY: clean
clean: ## Clean generated files
	-rm -rf dist qtile.egg-info docs/_build build/ .mypy_cache/ .pytest_cache/ .eggs/

.PHONY: update-flake
update-flake: ## Update the Nix flake.lock file, requires Nix installed with flake support, see: https://nixos.wiki/wiki/Flakes
	nix flake update

.PHONY: build-wayland
build-wayland: ## Build wayland backend
	@python libqtile/backend/wayland/cffi/build.py

.PHONY: build-wayland-debug
build-wayland-debug: ## Build wayland backend with debug symbols
	@echo "Building wayland backend with debug symbols."
	@python libqtile/backend/wayland/cffi/build.py --debug

.PHONY: build-wayland-asan
build-wayland-asan: ## Build wayland backend with address sanitisation support.
	@echo "Building wayland backend with address sanitisation support."
	@echo "When starting qtile, you'll need to set 'LD_PRELOAD=$(gcc -print-file-name=libasan.so)' first."
	@python libqtile/backend/wayland/cffi/build.py --asan
