# Releasing to mock-prod

Mock-prod deploys are **tag-driven**, with tests and render completed **before** human approval, and Snowflake changes applied **only after** approval.

## Tag convention

| Tag | Purpose |
|-----|---------|
| `release-v1.0.0-rc.1` | Release candidate → mock-prod (`TEST.GITHUB_DEPLOY_*`) |
| `release-v1.0.0-rc.2` | Next RC after fixes |
| `release-v1.0.0` | Final release (future real prod — not automated yet) |

**Pattern (mock-prod):** `release-vMAJOR.MINOR.PATCH-rc.N`

Examples:

```bash
git tag release-v1.0.0-rc.1
git push origin release-v1.0.0-rc.1
```

Optional: create a [GitHub Release](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository) from the same tag for release notes and audit.

## Workflow: Release mock prod

Triggered by:

- Push of a matching tag
- Manual **workflow_dispatch** with tag input (re-run or hotfix same tag after infra failure)

### Job 1 — `prepare-release` (no Snowflake writes)

1. Checkout the tag
2. Validate tag matches `release-v*.*.*-rc.*`
3. Run `make ci` (render tests for all contexts)
4. Render `mock-prod` → `build/mock-prod/`
5. Write `deploy-paths.txt` (manifest order)
6. Upload artifact `mock-prod-sql-<tag>`

### Job 2 — `deploy-release` (Snowflake apply)

1. Waits for **mock-prod** environment approval (required reviewers)
2. Downloads the **same artifact** from job 1
3. Applies SQL files listed in `deploy-paths.txt`

What gets approved is exactly what was rendered in prepare — not a fresh render.

## GitHub setup

### Environment `mock-prod`

- **Required reviewers:** enable (your boss + others as needed)
- **Deployment tags:** restrict to `release-v*-*-rc.*` or `release-v[0-9]+.[0-9]+.[0-9]+-rc.[0-9]+` if GitHub offers pattern UI
- **Secrets:** same Snowflake / VPN / OTP as staging

### Environment `staging`

Unchanged — `main` and `cp-*` only; not used for release deploy.

## Release checklist

1. Merge to `main`; confirm **Deploy staging** succeeded.
2. Create and push RC tag: `release-v1.2.0-rc.1`.
3. Open **Actions → Release mock prod**; confirm **prepare-release** is green.
4. Review job summary (SQL paths, target `TEST.GITHUB_DEPLOY_METRICS`).
5. Approve **deploy-release** when ready.
6. Verify in Snowflake:

```sql
CALL TEST.GITHUB_DEPLOY_METRICS.RECORD_STAT('release-test', 'test', 'TEST_STAT', 'Smoke', 'SUM', 1.0, '{}');
```

7. If fixes needed: merge to `main`, tag `release-v1.2.0-rc.2`, repeat.

## Local dry-run

```bash
git checkout release-v1.0.0-rc.1   # or your branch
make ci
python scripts/render_sql.py mock-prod --list
python scripts/write_deploy_paths.py mock-prod -o build/mock-prod/deploy-paths.txt
cat build/mock-prod/deploy-paths.txt
```
