"""Settings must tolerate empty-string env vars.

CI maps `AIRADAR_TG_API_ID: ${{ secrets.AIRADAR_TG_API_ID }}`; an unset secret
becomes "" in the environment. An int field choking on "" used to crash the
whole app at startup (every CLI/collector builds Settings). Guard against it.
"""
from __future__ import annotations

from aiapiradar.config import Settings


def test_empty_tg_api_id_does_not_crash(monkeypatch):
    monkeypatch.setenv("AIRADAR_TG_API_ID", "")
    s = Settings(_env_file=None)
    assert s.tg_api_id == 0


def test_tg_api_id_parses_real_int(monkeypatch):
    monkeypatch.setenv("AIRADAR_TG_API_ID", "12345")
    s = Settings(_env_file=None)
    assert s.tg_api_id == 12345
