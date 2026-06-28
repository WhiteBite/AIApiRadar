"""Guard: worker/src/_generated.ts must stay in sync with the canonical Python.

If this fails, someone edited collector_meta.py / app_defaults.py (or the
generated file) without regenerating.
Fix: `python -m scripts.gen_worker_constants`.
"""
from pathlib import Path

from scripts.gen_worker_constants import GENERATED_PATH, render


def _norm(s: str) -> str:
    return s.replace("\r\n", "\n")


def test_worker_constants_in_sync():
    on_disk = _norm(Path(GENERATED_PATH).read_text(encoding="utf-8"))
    expected = _norm(render())
    assert on_disk == expected, (
        "worker/src/_generated.ts is out of sync with the canonical Python "
        "sources — run `python -m scripts.gen_worker_constants`"
    )
