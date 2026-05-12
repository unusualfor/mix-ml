"""Tests for the inventory page (read-only bottle browser)."""

from unittest.mock import patch

# --- Mock data ---

_BOTTLES_RESPONSE = {
    "total": 3,
    "items": [
        {
            "id": 1, "class_id": 10, "class_name": "London Dry Gin",
            "family_name": "Gin", "brand": "Tanqueray", "label": "No. Ten",
            "abv": 47.3, "on_hand": True,
            "flavor_profile": {
                "sweet": 1, "bitter": 1, "sour": 1, "citrusy": 5,
                "fruity": 0, "herbal": 2, "floral": 3, "spicy": 2,
                "smoky": 0, "vanilla": 0, "woody": 0, "minty": 0,
                "earthy": 0, "umami": 0, "body": 2, "intensity": 4,
            },
            "notes": None, "added_at": "2026-01-01T00:00:00Z",
        },
        {
            "id": 2, "class_id": 20, "class_name": "Campari",
            "family_name": "Bitter Italiano", "brand": "Campari", "label": None,
            "abv": 25.0, "on_hand": True,
            "flavor_profile": {
                "sweet": 2, "bitter": 5, "sour": 0, "citrusy": 3,
                "fruity": 1, "herbal": 3, "floral": 0, "spicy": 1,
                "smoky": 0, "vanilla": 0, "woody": 0, "minty": 0,
                "earthy": 0, "umami": 0, "body": 3, "intensity": 5,
            },
            "notes": None, "added_at": "2026-01-01T00:00:00Z",
        },
        {
            "id": 3, "class_id": 30, "class_name": "Amaro Montenegro",
            "family_name": "Amaro", "brand": "Montenegro", "label": None,
            "abv": 23.0, "on_hand": False,
            "flavor_profile": {
                "sweet": 3, "bitter": 3, "sour": 0, "citrusy": 2,
                "fruity": 2, "herbal": 4, "floral": 2, "spicy": 1,
                "smoky": 0, "vanilla": 1, "woody": 1, "minty": 0,
                "earthy": 0, "umami": 0, "body": 2, "intensity": 3,
            },
            "notes": None, "added_at": "2026-01-01T00:00:00Z",
        },
    ],
}

_BOTTLES_ON_HAND_ONLY = {
    "total": 2,
    "items": [b for b in _BOTTLES_RESPONSE["items"] if b["on_hand"]],
}

_BOTTLES_NOT_ON_HAND_ONLY = {
    "total": 1,
    "items": [b for b in _BOTTLES_RESPONSE["items"] if not b["on_hand"]],
}

_BOTTLES_EMPTY = {"total": 0, "items": []}

_PATCH = "app.routers.inventory.fetch_all_bottles"
_PATCH_SINGLE = "app.routers.inventory.fetch_bottle_by_id"


def test_inventory_returns_200_and_lists_bottles(client):
    with patch(_PATCH, return_value=_BOTTLES_RESPONSE):
        resp = client.get("/inventory")
    assert resp.status_code == 200
    assert "Tanqueray" in resp.text
    assert "Campari" in resp.text
    assert "Montenegro" in resp.text


def test_inventory_groups_by_family(client):
    with patch(_PATCH, return_value=_BOTTLES_RESPONSE):
        resp = client.get("/inventory")
    html = resp.text
    # Pinned families appear before alphabetical ones
    gin_pos = html.index("Gin")
    amaro_pos = html.index("Amaro")
    bitter_pos = html.index("Bitter Italiano")
    # Gin and Bitter Italiano are pinned higher than Amaro
    assert gin_pos < amaro_pos or bitter_pos < amaro_pos


def test_inventory_shows_count_summary(client):
    with patch(_PATCH, return_value=_BOTTLES_RESPONSE):
        resp = client.get("/inventory")
    assert "3 bottles" in resp.text
    assert "3 families" in resp.text


def test_inventory_filter_on_hand(client):
    with patch(_PATCH, return_value=_BOTTLES_ON_HAND_ONLY):
        resp = client.get("/inventory?filter=on_hand")
    assert resp.status_code == 200
    assert "Tanqueray" in resp.text
    assert "Montenegro" not in resp.text


def test_inventory_filter_not_on_hand_shows_empty_if_no_data(client):
    with patch(_PATCH, return_value=_BOTTLES_EMPTY):
        resp = client.get("/inventory?filter=not_on_hand")
    assert resp.status_code == 200
    assert "No bottles found" in resp.text


def test_bottle_card_collapsed_by_default(client):
    with patch(_PATCH, return_value=_BOTTLES_RESPONSE):
        resp = client.get("/inventory")
    html = resp.text
    # Cards link to profile expand endpoint
    assert 'hx-get="/inventory/1/profile"' in html
    # Flavor bars not shown in collapsed view
    assert "Flavor profile" not in html


def test_bottle_card_expanded_shows_flavor_profile_bars(client):
    bottle = _BOTTLES_RESPONSE["items"][0]  # Tanqueray
    with patch(_PATCH_SINGLE, return_value=bottle):
        resp = client.get("/inventory/1/profile")
    assert resp.status_code == 200
    html = resp.text
    assert "Flavor profile" in html
    # Check bar width is computed (citrusy=5 → 100%)
    assert 'style="width: 100%"' in html
    # Close button present
    assert 'hx-get="/inventory/1"' in html


def test_bottle_card_expanded_groups_gustative_and_structural(client):
    bottle = _BOTTLES_RESPONSE["items"][0]
    with patch(_PATCH_SINGLE, return_value=bottle):
        resp = client.get("/inventory/1/profile")
    html = resp.text
    assert "Taste" in html
    assert "Structural" in html
    # body and intensity are structural
    assert "body" in html
    assert "intensity" in html


def test_inventory_partial_response_for_htmx_filter(client):
    with patch(_PATCH, return_value=_BOTTLES_RESPONSE):
        resp = client.get("/inventory?filter=all", headers={"HX-Request": "true"})
    html = resp.text
    # Partial should NOT contain full page layout (no <html> tag)
    assert "<html" not in html
    # But should contain the grid content
    assert "Tanqueray" in html


def test_no_post_or_patch_endpoints_exposed(client):
    """Safety check: inventory is read-only, no mutation endpoints."""
    resp_post = client.post("/inventory")
    assert resp_post.status_code == 405

    resp_patch = client.patch("/inventory/1")
    assert resp_patch.status_code in (405, 404)

    resp_delete = client.delete("/inventory/1")
    assert resp_delete.status_code in (405, 404)


def test_navigation_link_active_for_inventory_page(client):
    with patch(_PATCH, return_value=_BOTTLES_RESPONSE):
        resp = client.get("/inventory")
    html = resp.text
    # The Inventory nav link should have the active class
    assert "Inventory" in html
    # Check the inventory link exists as an <a> tag (not disabled span)
    assert 'href="/inventory"' in html
