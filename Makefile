# Local: make setup once, then make test (or make ci)
# CI:    pip install -r requirements.txt && make ci
VENV := .venv
VENV_PYTHON := $(VENV)/bin/python
PIP := $(if $(wildcard $(VENV_PYTHON)),$(VENV)/bin/pip,pip3)
PYTHON := $(if $(wildcard $(VENV_PYTHON)),$(VENV_PYTHON),python3)

.PHONY: setup install ci test validate render-staging render-mock-prod check-rendered

setup:
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -r requirements.txt

install:
	$(PIP) install -q -r requirements.txt

# Same checks as GitHub Actions ci.yml
ci: validate render-staging render-mock-prod check-rendered

# Local: ensure venv exists, install deps, run ci
test: install ci

validate:
	$(PYTHON) scripts/render_sql.py --validate-sources-only

render-staging:
	$(PYTHON) scripts/render_sql.py staging --list

render-mock-prod:
	$(PYTHON) scripts/render_sql.py mock-prod --list

check-rendered:
	@test -f build/staging/sql/procedures/metrics/record_stat.sql || \
		(echo "Missing rendered staging output; run make render-staging first" >&2; exit 1)
	@test -f build/mock-prod/sql/procedures/metrics/record_stat.sql || \
		(echo "Missing rendered mock-prod output; run make render-mock-prod first" >&2; exit 1)
	@if diff -q build/staging/sql/procedures/metrics/record_stat.sql \
	        build/mock-prod/sql/procedures/metrics/record_stat.sql >/dev/null 2>&1; then \
		echo "ERROR: staging and mock-prod procedure renders must differ" >&2; exit 1; \
	fi
	@if diff -q build/staging/sql/ddl/metrics/001_stats_table.sql \
	        build/mock-prod/sql/ddl/metrics/001_stats_table.sql >/dev/null 2>&1; then \
		echo "ERROR: staging and mock-prod DDL renders must differ" >&2; exit 1; \
	fi
	@if grep -r '{{' build/staging build/mock-prod --include='*.sql' >/dev/null 2>&1; then \
		echo "Unrendered Jinja tokens found under build/" >&2; exit 1; \
	fi
