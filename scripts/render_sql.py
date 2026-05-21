#!/usr/bin/env python3
"""Render SQL Jinja templates for a target environment (local + CI)."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any, Callable

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_DIR = REPO_ROOT / "config" / "environments"
FEATURES_PATH = REPO_ROOT / "config" / "features.yaml"
MANIFEST_PATH = REPO_ROOT / "config" / "manifest.yaml"
BUILD_DIR = REPO_ROOT / "build"

FORBIDDEN_IN_SOURCE = (
    "LOCATION_STREAM.",
    "TEST.PUBLIC.",
    "TEST.GITHUB_DEPLOY.",
    "TEST.STAGING_",
    "TEST.GITHUB_DEPLOY_",
)

SCHEMA_PREFIX_RE = re.compile(r"^[A-Z][A-Z0-9_]*_$")
DEFAULT_BRANCH_PATTERN = re.compile(r"^cp-[a-zA-Z0-9._-]+$")

jinja = Environment(
    loader=FileSystemLoader(REPO_ROOT),
    undefined=StrictUndefined,
    keep_trailing_newline=True,
)


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}")
    return data


def load_features() -> dict:
    if FEATURES_PATH.is_file():
        return load_yaml(FEATURES_PATH)
    return {}


def normalize_schema_prefix(raw: object, label: str) -> str:
    """Return prefix (e.g. STAGING_) or empty string for prod (no prefix)."""
    if raw is None:
        return ""
    prefix = str(raw).strip().upper()
    if not prefix:
        return ""
    if not prefix.endswith("_"):
        prefix += "_"
    if not SCHEMA_PREFIX_RE.match(prefix):
        raise ValueError(
            f"{label}: schema_prefix must be empty (prod) or uppercase letters/digits "
            f"with trailing underscore (e.g. STAGING_, GITHUB_DEPLOY_); got '{prefix}'"
        )
    return prefix


def branch_pattern() -> re.Pattern[str]:
    cfg = load_features()
    pattern = cfg.get("branch_pattern", "^cp-[a-zA-Z0-9._-]+$")
    return re.compile(str(pattern))


def feature_branch_database() -> str:
    return str(load_features().get("database", "TEST")).strip()


def max_schema_prefix_length() -> int:
    return int(load_features().get("max_schema_prefix_length", 50))


def validate_branch_name(branch: str) -> str:
    branch = branch.strip()
    if not branch:
        raise ValueError("Branch name is required")
    if not branch_pattern().match(branch):
        raise ValueError(
            f"Branch '{branch}' does not match feature branch pattern "
            f"({branch_pattern().pattern}). Only cp-* branches are supported."
        )
    return branch


def branch_to_schema_prefix(branch: str) -> str:
    """Derive schema prefix from git branch (e.g. cp-feature-1 -> CP_FEATURE_1_)."""
    branch = validate_branch_name(branch)
    normalized = branch.upper()
    normalized = re.sub(r"[^A-Z0-9]+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    prefix = f"{normalized}_"
    max_len = max_schema_prefix_length()
    if len(prefix) > max_len:
        prefix = prefix[:max_len]
        if not prefix.endswith("_"):
            prefix = prefix.rstrip("_") + "_"
    if not SCHEMA_PREFIX_RE.match(prefix):
        raise ValueError(f"Could not derive valid schema_prefix from branch '{branch}'")
    return prefix


def build_render_context(
    *,
    environment: str,
    database: str,
    schema_prefix: str,
    branch: str | None = None,
) -> dict[str, Any]:
    def schema_name(base: str) -> str:
        base = str(base).strip().upper()
        return f"{schema_prefix}{base}"

    def object_fqn(base_schema: str, object_name: str) -> str:
        return f"{database}.{schema_name(base_schema)}.{object_name}"

    metrics_schema = schema_name("METRICS")
    ctx: dict[str, Any] = {
        "environment": environment,
        "database": database,
        "schema_prefix": schema_prefix,
        # Full schema name (prefix + base), e.g. STAGING_METRICS, CP_FEATURE_1_METRICS, METRICS
        "schema": metrics_schema,
        "schema_name": schema_name,
        "object_fqn": object_fqn,
        "metrics_schema": metrics_schema,
        "fqn_metrics": f"{database}.{metrics_schema}",
    }
    if branch:
        ctx["branch"] = branch
    return ctx


def load_environment(name: str) -> dict[str, Any]:
    path = ENV_DIR / f"{name}.yaml"
    if not path.is_file():
        available = ", ".join(sorted(p.stem for p in ENV_DIR.glob("*.yaml"))) or "(none)"
        raise FileNotFoundError(f"Unknown environment '{name}'. Available: {available}")
    cfg = load_yaml(path)
    database = str(cfg.get("database", "")).strip()
    if not database:
        raise ValueError(f"{path} must define database")
    if "schema_prefix" not in cfg:
        raise ValueError(f'{path} must define schema_prefix (use "" for prod)')

    schema_prefix = normalize_schema_prefix(cfg["schema_prefix"], str(path))
    return build_render_context(
        environment=name,
        database=database,
        schema_prefix=schema_prefix,
    )


def load_branch(branch: str) -> dict[str, Any]:
    branch = validate_branch_name(branch)
    return build_render_context(
        environment=f"branch:{branch}",
        database=feature_branch_database(),
        schema_prefix=branch_to_schema_prefix(branch),
        branch=branch,
    )


def resolve_context(*, environment: str | None, branch: str | None) -> dict[str, Any]:
    if environment and branch:
        raise ValueError("Use either environment or --branch, not both")
    if branch:
        return load_branch(branch)
    if environment:
        return load_environment(environment)
    raise ValueError("environment or --branch is required")


def branch_output_slug(branch: str) -> str:
    return validate_branch_name(branch).replace("/", "-")


def manifest_paths() -> list[str]:
    objects = load_yaml(MANIFEST_PATH).get("objects") or []
    if not objects:
        raise ValueError(f"{MANIFEST_PATH} must define objects in deploy order")
    paths = []
    for obj in objects:
        rel = obj.get("path")
        if not rel:
            raise ValueError(f"Manifest object missing path: {obj}")
        paths.append(rel)
    return paths


def validate_sources() -> list[str]:
    errors = []
    for path in sorted((REPO_ROOT / "sql").rglob("*.sql")):
        text = path.read_text(encoding="utf-8")
        for needle in FORBIDDEN_IN_SOURCE:
            if needle in text:
                errors.append(f"{path.relative_to(REPO_ROOT)}: hard-coded '{needle}'")
    return errors


def render_context(ctx: dict[str, Any], output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for rel_path in manifest_paths():
        try:
            template = jinja.get_template(rel_path)
        except TemplateNotFound as exc:
            raise FileNotFoundError(f"Template not found: {rel_path}") from exc
        dest = output_dir / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(template.render(**ctx), encoding="utf-8")
        written.append(dest)

    meta = output_dir / ".render-env.yaml"
    meta.write_text(
        yaml.safe_dump(
            {k: v for k, v in ctx.items() if not callable(v)},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    written.append(meta)
    return written


def render(
    *,
    environment: str | None = None,
    branch: str | None = None,
    output_dir: Path | None = None,
) -> tuple[list[Path], dict[str, Any]]:
    errors = validate_sources()
    if errors:
        raise ValueError("Source validation failed:\n  " + "\n  ".join(errors))

    ctx = resolve_context(environment=environment, branch=branch)
    if output_dir is None:
        if branch:
            output_dir = BUILD_DIR / branch_output_slug(branch)
        else:
            output_dir = BUILD_DIR / str(ctx["environment"])
    written = render_context(ctx, output_dir)
    return written, ctx


def main() -> int:
    parser = argparse.ArgumentParser(description="Render SQL templates for Snowflake")
    parser.add_argument(
        "environment",
        nargs="?",
        help="Named environment (staging, mock-prod, prod)",
    )
    parser.add_argument(
        "--branch",
        help="Git branch for feature deploy (cp-*); derives schema_prefix, uses TEST db",
    )
    parser.add_argument("--output-dir", type=Path, help="default: build/<environment> or build/<branch>")
    parser.add_argument("--list", action="store_true", help="Print rendered paths (repo-relative)")
    parser.add_argument("--paths", action="store_true", help="Print rendered paths (absolute, manifest order)")
    parser.add_argument("--validate-sources-only", action="store_true")
    args = parser.parse_args()

    if args.validate_sources_only:
        errors = validate_sources()
        if errors:
            for e in errors:
                print(e, file=sys.stderr)
            return 1
        print("Source validation OK")
        return 0

    if not args.environment and not args.branch:
        parser.error("environment or --branch is required")

    try:
        written, ctx = render(
            environment=args.environment,
            branch=args.branch,
            output_dir=args.output_dir,
        )
    except (FileNotFoundError, ValueError, TemplateNotFound) as exc:
        print(exc, file=sys.stderr)
        return 1

    out = args.output_dir or (
        BUILD_DIR / branch_output_slug(args.branch)
        if args.branch
        else BUILD_DIR / str(ctx["environment"])
    )
    sql_count = len(written) - 1
    summary = f"Rendered {sql_count} file(s) -> {ctx['fqn_metrics']} in {out}"
    print(summary, file=sys.stderr if args.paths else sys.stdout)

    for path in written:
        if path.name == ".render-env.yaml":
            continue
        if args.list:
            print(path.relative_to(REPO_ROOT))
        if args.paths:
            print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
