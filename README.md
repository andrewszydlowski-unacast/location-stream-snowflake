# location-stream-snowflake

Snowflake procedures and DDL for LocationStream pipelines. SQL under `sql/` is **Jinja2**; render per environment before deploy.

## Naming model

| Piece | Source | Example (staging) |
|-------|--------|-------------------|
| **Database** | Environment config | `TEST` |
| **Schema prefix** | Environment config (uppercase + trailing `_`) | `STAGING_` |
| **Base schema** | Hardcoded in SQL templates | `METRICS` |
| **Full schema** | `prefix` + `base` | `STAGING_METRICS` |

Rendered FQN example: `TEST.STAGING_METRICS.RECORD_STAT`

Mock prod uses prefix `GITHUB_DEPLOY_` → schema `GITHUB_DEPLOY_METRICS`.

**Production** uses an **empty** `schema_prefix` → schema `METRICS` on database `LOCATION_STREAM` (same as flowdefs). Prod config exists for render/CI; deploy workflow is not wired yet.

## Layout

```
sql/                          # Jinja templates (hardcoded base schemas: METRICS, RAW, …)
config/
  environments/staging.yaml   # database + schema_prefix
  manifest.yaml               # deploy order
scripts/render_sql.py
build/                        # rendered SQL (gitignored)
```

## Template variables

| Variable | Description |
|----------|-------------|
| `{{ database }}` | From env config |
| `{{ schema_prefix }}` | From env config, normalized to `STAGING_` style |
| `{{ schema }}` | Full metrics schema name (`STAGING_METRICS`, `CP_FEATURE_1_METRICS`, `METRICS` in prod) |
| `{{ schema_prefix }}METRICS` | Same as `{{ schema }}` when base is METRICS |

Optional Jinja callables (for complex templates):

- `{{ schema_name('METRICS') }}` → `STAGING_METRICS`
- `{{ object_fqn('METRICS', 'STATS') }}` → `TEST.STAGING_METRICS.STATS`

Do not hard-code environment-specific FQNs in `sql/` (e.g. `TEST.PUBLIC.`, `TEST.STAGING_`).

## Environment config

```yaml
# config/environments/staging.yaml
database: TEST
schema_prefix: STAGING_   # uppercase, trailing underscore required

# config/environments/prod.yaml
database: LOCATION_STREAM
schema_prefix: ""           # empty = no prefix (production layout)
```

## Local setup

```bash
make setup
make test
cat build/staging/sql/procedures/metrics/record_stat.sql
```

## Snowflake setup (per env)

Deploy creates schemas via `000_create_metrics_schema.sql`. Grant your deploy role `CREATE SCHEMA` / `USAGE` on `TEST` as needed.

## Feature branches (`cp-*`)

Push to a branch matching `cp-*` (e.g. `cp-feature-1`) triggers **Deploy feature branch**:

| Branch | Auto `schema_prefix` | Example schema |
|--------|----------------------|----------------|
| `cp-feature-1` | `CP_FEATURE_1_` | `CP_FEATURE_1_METRICS` |

Rules (see `config/features.yaml`):

- Database is always `TEST` for feature branches
- Branch name → uppercase, non-alphanumerics → `_`, trailing `_`
- Prod / `main` staging prefixes are never used for `cp-*` deploys

Local preview:

```bash
make render-branch BRANCH=cp-feature-1
# -> build/cp-feature-1/... targeting TEST.CP_FEATURE_1_METRICS

python scripts/render_sql.py --branch cp-feature-1 --list
```

## CI / deploy

| Target | GitHub Environment | Example schema | Deploy |
|--------|-------------------|----------------|--------|
| `staging.yaml` | `staging` | `STAGING_METRICS` | Push to `main` |
| `cp-*` branches | `staging` (same secrets) | `CP_FEATURE_1_METRICS` | Push to `cp-*` |
| `mock-prod.yaml` | `mock-prod` | `GITHUB_DEPLOY_METRICS` | Tag `release-v*.*.*-rc.*` → [docs/RELEASE.md](docs/RELEASE.md) |
| `prod.yaml` | `prod` (future) | `METRICS` | Tag `release-v*.*.*` (not implemented) |

## Verify (staging)

```sql
SHOW SCHEMAS LIKE 'STAGING_%' IN DATABASE TEST;
CALL TEST.STAGING_METRICS.RECORD_STAT('test-job', 'test', 'TEST_STAT', 'Smoke', 'SUM', 1.0, '{}');
SELECT * FROM TEST.STAGING_METRICS.STATS WHERE JOBID = 'test-job';
```

## Mock-prod releases

Push an RC tag (see **[docs/RELEASE.md](docs/RELEASE.md)**):

```bash
git tag release-v1.0.0-rc.1
git push origin release-v1.0.0-rc.1
```

Workflow: **prepare** (CI + render) → **approve** `mock-prod` environment → **deploy** to Snowflake.

## Verify (feature branch)

```sql
SHOW SCHEMAS LIKE 'CP_FEATURE_1_%' IN DATABASE TEST;
CALL TEST.CP_FEATURE_1_METRICS.RECORD_STAT('test-job', 'test', 'TEST_STAT', 'Smoke', 'SUM', 1.0, '{}');
```
