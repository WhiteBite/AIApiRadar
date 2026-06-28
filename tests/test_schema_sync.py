"""Guard: db/schema.sql must stay in sync with the canonical SCHEMA_SQL.

If this fails, someone edited SCHEMA_SQL (or schema.sql) without regenerating.
Fix: `python -m scripts.gen_schema`.
"""
from pathlib import Path

from scripts.gen_schema import SCHEMA_PATH, render


def _norm(s: str) -> str:
    return s.replace("\r\n", "\n")


def test_schema_sql_in_sync():
    on_disk = _norm(Path(SCHEMA_PATH).read_text(encoding="utf-8"))
    expected = _norm(render())
    assert on_disk == expected, (
        "db/schema.sql is out of sync with db/base.py SCHEMA_SQL — "
        "run `python -m scripts.gen_schema`"
    )
