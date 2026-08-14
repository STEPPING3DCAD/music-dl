"""Tests for FastAPI lifespan startup behavior."""

from __future__ import annotations

import warnings

from fastapi.testclient import TestClient

from tidal_dl.gui import create_app


def test_create_app_does_not_emit_on_event_deprecation_warning():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        create_app(port=8765)

    on_event_deprecations = [
        w for w in caught
        if issubclass(w.category, DeprecationWarning)
        and "on_event" in str(w.message)
        and "deprecated" in str(w.message).lower()
    ]
    assert on_event_deprecations == []


def test_gui_lifespan_invokes_noninteractive_source_resolution(tmp_path):
    assert not (tmp_path / "token.json").exists()

    app = create_app(port=8765, job_db_path=tmp_path / "jobs.db")
    with TestClient(app) as client:
        response = client.get("/api/server/health", headers={"host": "localhost:8765"})

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert app.state.source_restore_attempted is True
    assert app.state.source_restored is False
    assert app.state.source_restore_error is None


def test_health_returns_structured_daemon_state():
    with TestClient(create_app(port=8765)) as client:
        resp = client.get("/api/server/health", headers={"host": "localhost:8765"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["app"] == "music-dl"
    assert data["status"] == "ready"
    assert data["host"] == "127.0.0.1"
    assert data["port"] == 8765
    assert data["base_url"] == "http://127.0.0.1:8765"
    assert data["health_url"] == "http://127.0.0.1:8765/api/server/health"
