#!/usr/bin/env python3
"""Write manifest-ordered deploy paths for a rendered environment (used by release workflow)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from render_sql import BUILD_DIR, manifest_paths  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("environment", help="e.g. mock-prod, staging")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Write paths to file (default: stdout, repo-relative paths)",
    )
    args = parser.parse_args()

    build_root = BUILD_DIR / args.environment
    lines = [str(build_root / rel) for rel in manifest_paths()]

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        for line in lines:
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
