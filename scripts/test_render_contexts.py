#!/usr/bin/env python3
"""Smoke-test render for all deployment contexts (run in CI via make)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from render_sql import branch_to_schema_prefix, render  # noqa: E402


def assert_contains(path: Path, needle: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if needle not in text:
        raise AssertionError(f"{label}: expected '{needle}' in {path}")


def main() -> int:
    cases = [
        ("staging", None, "TEST.STAGING_METRICS.RECORD_STAT"),
        ("mock-prod", None, "TEST.GITHUB_DEPLOY_METRICS.RECORD_STAT"),
        ("prod", None, "LOCATION_STREAM.METRICS.RECORD_STAT"),
        (None, "cp-feature-1", "TEST.CP_FEATURE_1_METRICS.RECORD_STAT"),
    ]
    for env, branch, expected in cases:
        written, ctx = render(environment=env, branch=branch)
        proc = next(p for p in written if p.name == "record_stat.sql")
        assert_contains(proc, expected, f"env={env} branch={branch}")
        print(f"OK {expected}")

    assert branch_to_schema_prefix("cp-feature-1") == "CP_FEATURE_1_"
    print("OK branch_to_schema_prefix")
    return 0


if __name__ == "__main__":
    sys.exit(main())
