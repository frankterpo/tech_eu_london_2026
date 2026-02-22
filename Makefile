.PHONY: lint test schema smoke-local smoke-cloud bootstrap install install-browsers

install:
	pip install -e cli/
	$(MAKE) install-browsers

install-browsers:
	@if [ "$$SKIP_PLAYWRIGHT_INSTALL" = "1" ]; then \
		echo "Skipping Playwright browser install (SKIP_PLAYWRIGHT_INSTALL=1)"; \
	else \
		python3 -m playwright install chromium; \
	fi

bootstrap:
	agent bootstrap

lint:
	ruff check cli/src
	ruff format --check cli/src

test:
	pytest cli/tests

schema:
	# TODO: Implement schema validation command
	@echo "Schema validation not yet implemented"

smoke-local:
	agent smoke-local

smoke-cloud:
	agent cloud smoke
