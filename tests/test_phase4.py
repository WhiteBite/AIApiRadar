"""Phase 4 tests: API endpoints + dashboard rendering via TestClient."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AIRADAR_DB_URL", f"sqlite:///{tmp_path / 'p4.db'}")
    import aiapiradar.config as config
    import aiapiradar.db as db
    config.get_settings.cache_clear()
    db._engine = None
    db._SessionFactory = None
    db.init_db()

    from aiapiradar.models import Service, Offer, utcnow
    with db.session_scope() as s:
        svc = Service(canonical_domain="freemodel.dev", name="FreeModel", type="relay",
                      status="active", reliability=0.9, engine="new-api")
        s.add(svc)
        s.flush()
        s.add(Offer(service_id=svc.id, type="relay", amount=300, currency="USD",
                    models=["gpt", "claude"], claim_steps="Sign up, get key.",
                    url="https://freemodel.dev", score=0.82, first_seen_at=utcnow()))
        svc2 = Service(canonical_domain="tiny.ai", name="Tiny", type="saas_trial", status="dead")
        s.add(svc2)
        s.flush()
        s.add(Offer(service_id=svc2.id, type="saas_trial", amount=5, score=0.1,
                    first_seen_at=utcnow()))

    from aiapiradar.web import create_app
    return TestClient(create_app())


def test_api_stats(client):
    r = client.get("/api/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["services"] == 2 and data["offers"] == 2
    assert data["active"] == 1 and data["dead"] == 1


def test_api_offers_sorted_and_shaped(client):
    r = client.get("/api/offers")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 2
    # sorted by score desc
    assert items[0]["domain"] == "freemodel.dev"
    assert items[0]["amount"] == 300 and "gpt" in items[0]["models"]
    assert items[0]["engine"] == "new-api"


def test_api_offers_filters(client):
    assert len(client.get("/api/offers?min_amount=100").json()["items"]) == 1
    assert len(client.get("/api/offers?type=relay").json()["items"]) == 1
    assert len(client.get("/api/offers?status=dead").json()["items"]) == 1
    assert len(client.get("/api/offers?model=claude").json()["items"]) == 1
    assert len(client.get("/api/offers?q=freemodel").json()["items"]) == 1


def test_api_service_detail(client):
    offers = client.get("/api/offers").json()["items"]
    sid = offers[0]["service_id"]
    r = client.get(f"/api/services/{sid}")
    assert r.status_code == 200
    assert r.json()["domain"] == "freemodel.dev"
    assert len(r.json()["offers"]) == 1
    assert client.get("/api/services/99999").status_code == 404


def test_dashboard_and_detail_html(client):
    r = client.get("/")
    assert r.status_code == 200 and "freemodel.dev" in r.text
    sid = client.get("/api/offers").json()["items"][0]["service_id"]
    r2 = client.get(f"/services/{sid}")
    assert r2.status_code == 200 and "How to claim" in r2.text
