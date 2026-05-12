"""Tests for the home page and cocktail list endpoints."""

from unittest.mock import patch

import httpx

# Sample backend response
_SAMPLE_RESPONSE = {
    "summary": {"total_recipes": 77, "can_make": 3, "cannot_make": 74, "on_hand_classes": 5},
    "items": [
        {"id": 1, "name": "Negroni", "iba_category": "unforgettable", "glass": "Old Fashioned", "can_make": True, "missing_count": 0, "missing_classes": []},
        {"id": 2, "name": "Moscow Mule", "iba_category": "contemporary", "glass": "Highball", "can_make": True, "missing_count": 0, "missing_classes": []},
        {"id": 3, "name": "Spritz", "iba_category": "new_era", "glass": "Wine glass", "can_make": True, "missing_count": 0, "missing_classes": []},
    ],
}

_EMPTY_RESPONSE = {
    "summary": {"total_recipes": 77, "can_make": 0, "cannot_make": 77, "on_hand_classes": 0},
    "items": [],
}


def _mock_fetch(data):
    return patch("app.routers.home.fetch_cocktails_can_make_now", return_value=data)


def _mock_fetch_error():
    return patch(
        "app.routers.home.fetch_cocktails_can_make_now",
        side_effect=httpx.ConnectError("connection refused"),
    )


# ── Home page ────────────────────────────────────────────────────────

def test_home_returns_200_and_html(client):
    with _mock_fetch(_SAMPLE_RESPONSE):
        resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "<!DOCTYPE html>" in resp.text


def test_home_lists_cocktails_from_backend(client):
    with _mock_fetch(_SAMPLE_RESPONSE):
        resp = client.get("/")
    assert "Negroni" in resp.text
    assert "Moscow Mule" in resp.text
    assert "Spritz" in resp.text


def test_filter_returns_only_partial(client):
    """HTMX request should return partial without full HTML shell."""
    with _mock_fetch(_SAMPLE_RESPONSE):
        resp = client.get(
            "/cocktails/can-make-now?category=unforgettable",
            headers={"HX-Request": "true"},
        )
    assert resp.status_code == 200
    assert "<!DOCTYPE html>" not in resp.text
    # Should still contain cocktail content
    assert "Negroni" in resp.text


def test_empty_state_when_zero_cocktails(client):
    with _mock_fetch(_EMPTY_RESPONSE):
        resp = client.get("/")
    assert resp.status_code == 200
    assert "No cocktails available" in resp.text
    assert "Coming soon" in resp.text


def test_backend_unreachable_shows_error_page(client):
    with _mock_fetch_error():
        resp = client.get("/")
    assert resp.status_code == 200
    assert "Backend unreachable" in resp.text


# ── Health endpoints ─────────────────────────────────────────────────

def test_healthz_returns_ok(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_readyz_pings_backend_health(client):
    with patch("app.routers.health.ping_backend", return_value=True):
        resp = client.get("/readyz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    with patch("app.routers.health.ping_backend", return_value=False):
        resp = client.get("/readyz")
    assert resp.status_code == 503
