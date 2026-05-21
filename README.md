# location-stream-snowflake

Snowflake procedures and DDL for LocationStream pipelines. SQL under `sql/` is **Jinja2**; render per environment before deploy.

## Layout

```
sql/                          # Jinja templates
config/
  environments/staging.yaml   # database + schema
  manifest.yaml               # deploy order (list order = apply order)
scripts/render_sql.py         # Jinja render (local + CI)
build/                        # rendered SQL (gitignored)
Makefile                      # local shortcuts
```

## Template variables

| Variable | Staging | Mock prod |
|----------|---------|-----------|
| `{{ database }}` | `TEST` | `TEST` |
| `{{ schema }}` | `PUBLIC` | `GITHUB_DEPLOY` |
| `{{ fqn }}` | `TEST.PUBLIC` | `TEST.GITHUB_DEPLOY` |

Also available in templates: `{{ environment }}` (config file name).

Do not hard-code `LOCATION_STREAM.*`, `TEST.PUBLIC.*`, or `TEST.GITHUB_DEPLOY.*` in `sql/`.

## Local setup

One-time venv:

```bash
make setup
```

Run the same checks as GitHub Actions:

```bash
make test    # install deps + validate + render both envs + diff
# or, if .venv already exists:
make ci
```

Individual steps:

```bash
make validate
make render-staging
make render-mock-prod
```

Inspect output:

```bash
cat build/staging/sql/procedures/metrics/record_stat.sql
```

Deploy rendered files locally:

```bash
.venv/bin/python scripts/render_sql.py staging
while IFS= read -r f; do snow sql -f "$f"; done < <(.venv/bin/python scripts/render_sql.py staging --paths)
```

## Environments

| Config | GitHub Environment | Snowflake |
|--------|-------------------|-----------|
| `staging.yaml` | `staging` | `TEST.PUBLIC` |
| `mock-prod.yaml` | `mock-prod` | `TEST.GITHUB_DEPLOY` |

```sql
CREATE SCHEMA IF NOT EXISTS TEST.GITHUB_DEPLOY;
```

## CI / deploy

- `ci.yml` — runs `make ci` on every PR and push to `main`
- `deploy-staging.yml` — push `main` → render → `snow sql`
- `deploy-mock-prod.yml` — manual dispatch + approval

## Verify (staging)

```sql
CALL TEST.PUBLIC.RECORD_STAT('test-job', 'test', 'TEST_STAT', 'Smoke', 'SUM', 1.0, '{}');
SELECT * FROM TEST.PUBLIC.STATS WHERE JOBID = 'test-job';
```
