#!/usr/bin/env python3
"""Render SQL Jinja templates for a target environment (local + CI)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_DIR = REPO_ROOT / "config" / "environments"
MANIFEST_PATH = REPO_ROOT / "config" / "manifest.yaml"
BUILD_DIR = REPO_ROOT / "build"

FORBIDDEN_IN_SOURCE = (
    "LOCATION_STREAM.",
    "TEST.PUBLIC.",
    "TEST.GITHUB_DEPLOY.",
)

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


def load_environment(name: str) -> dict[str, str]:
    path = ENV_DIR / f"{name}.yaml"
    if not path.is_file():
        available = ", ".join(sorted(p.stem for p in ENV_DIR.glob("*.yaml"))) or "(none)"
        raise FileNotFoundError(f"Unknown environment '{name}'. Available: {available}")
    cfg = load_yaml(path)
    database = str(cfg.get("database", "")).strip()
    schema = str(cfg.get("schema", "")).strip()
    if not database or not schema:
        raise ValueError(f"{path} must define database and schema")
    return {
        "environment": name,
        "database": database,
        "schema": schema,
        "fqn": f"{database}.{schema}",
    }


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


def render(environment: str, output_dir: Path) -> list[Path]:
    errors = validate_sources()
    if errors:
        raise ValueError("Source validation failed:\n  " + "\n  ".join(errors))

    ctx = load_environment(environment)
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
    meta.write_text(yaml.safe_dump(ctx, sort_keys=False), encoding="utf-8")
    written.append(meta)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="Render SQL templates for Snowflake")
    parser.add_argument("environment", nargs="?", help="e.g. staging, mock-prod")
    parser.add_argument("--output-dir", type=Path, help="default: build/<environment>")
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

    if not args.environment:
        parser.error("environment is required unless using --validate-sources-only")

    out = args.output_dir or (BUILD_DIR / args.environment)
    try:
        written = render(args.environment, out)
    except (FileNotFoundError, ValueError, TemplateNotFound) as exc:
        print(exc, file=sys.stderr)
        return 1

    ctx = load_environment(args.environment)
    sql_count = len(written) - 1
    summary = f"Rendered {sql_count} file(s) -> {ctx['fqn']} in {out}"
    # --paths is consumed by shell loops; keep stdout path-only
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
