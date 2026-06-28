"""Generate aiapiradar/db/schema.sql from the canonical SCHEMA_SQL.

`db/base.py::SCHEMA_SQL` is the single source of truth (it is what `init_db()`
actually runs). `db/schema.sql` is a convenience artifact used to bootstrap a
fresh Cloudflare D1 database via wrangler (see worker/README.md). Keeping it
hand-maintained caused drift (e.g. the `conditions` / `topic` columns had to be
added in multiple places). This script regenerates it so there is exactly one
source; `tests/test_schema_sync.py` fails if they diverge.

Usage:
    python -m scripts.gen_schema
"""
from __future__ import annotations

from pathlib import Path

HEADER = (
    "-- AUTO-GENERATED from aiapiradar/db/base.py (SCHEMA_SQL).\n"
    "-- Do not edit by hand — regenerate with:  python -m scripts.gen_schema\n"
)

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "aiapiradar" / "db" / "schema.sql"


def render() -> str:
    """Return the full schema.sql content (header + canonical DDL)."""
    from aiapiradar.db.base import SCHEMA_SQL

    return HEADER + "\n" + SCHEMA_SQL.lstrip("\n")


def main() -> None:
    content = render()
    with open(SCHEMA_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    print(f"wrote {SCHEMA_PATH} ({len(content)} bytes)")


if __name__ == "__main__":
    main()
