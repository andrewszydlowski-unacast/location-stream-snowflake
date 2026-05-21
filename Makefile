# Local: make setup once, then make test (or make ci)
# CI:    pip install -r requirements.txt && make ci
VENV := .venv
VENV_PYTHON := $(VENV)/bin/python
PIP := $(if $(wildcard $(VENV_PYTHON)),$(VENV)/bin/pip,pip3)
PYTHON := $(if $(wildcard $(VENV_PYTHON)),$(VENV_PYTHON),python3)

BRANCH ?= cp-feature-1

.PHONY: setup install ci test validate render-staging render-mock-prod render-prod render-branch check-rendered check-prod-render check-branch-render

setup:
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -r requirements.txt

install:
	$(PIP) install -q -r requirements.txt

# Same checks as GitHub Actions ci.yml
ci: validate test-render-contexts render-staging render-mock-prod render-prod render-branch check-rendered check-prod-render check-branch-render

# Local: ensure venv exists, install deps, run ci
test: install ci

validate:
	$(PYTHON) scripts/render_sql.py --validate-sources-only

test-render-contexts:
	$(PYTHON) scripts/test_render_contexts.py

render-staging:
	$(PYTHON) scripts/render_sql.py staging --list

render-mock-prod:
	$(PYTHON) scripts/render_sql.py mock-prod --list

render-prod:
	$(PYTHON) scripts/render_sql.py prod --list

render-branch:
	$(PYTHON) scripts/render_sql.py --branch $(BRANCH) --list

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
	@if grep -r '{{' build/staging build/mock-prod build/prod --include='*.sql' >/dev/null 2>&1; then \
		echo "Unrendered Jinja tokens found under build/" >&2; exit 1; \
	fi

check-prod-render:
	@test -f build/prod/sql/procedures/metrics/record_stat.sql || \
		(echo "Missing prod render; run make render-prod first" >&2; exit 1)
	@grep -q 'LOCATION_STREAM.METRICS.RECORD_STAT' build/prod/sql/procedures/metrics/record_stat.sql || \
		(echo "ERROR: prod must render LOCATION_STREAM.METRICS (no schema prefix)" >&2; exit 1)
	@if grep -E 'STAGING_|GITHUB_DEPLOY_' build/prod/sql/procedures/metrics/record_stat.sql >/dev/null; then \
		echo "ERROR: prod render must not include test schema prefixes" >&2; exit 1; \
	fi

check-branch-render:
	@test -f build/cp-feature-1/sql/procedures/metrics/record_stat.sql || \
		(echo "Missing branch render; run make render-branch first" >&2; exit 1)
	@grep -q 'TEST.CP_FEATURE_1_METRICS.RECORD_STAT' build/cp-feature-1/sql/procedures/metrics/record_stat.sql || \
		(echo "ERROR: cp-feature-1 must render TEST.CP_FEATURE_1_METRICS" >&2; exit 1)
