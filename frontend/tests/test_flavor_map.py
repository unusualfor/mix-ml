"""Tests for the flavor map feature (matrix heatmap + clusters)."""

from unittest.mock import patch, MagicMock

import pytest

from app.services.flavor_matrix_builder import (
    FlavorMatrixData,
    build_flavor_matrix,
    flavor_distance,
)
from app.services.flavor_matrix_renderer import render_flavor_matrix_svg, viridis_color

_PATCH_BOTTLES = "app.routers.inventory.fetch_all_bottles"

# --- Helpers ---

def _make_profile(**overrides):
    base = {
        "sweet": 0, "bitter": 0, "sour": 0, "citrusy": 0, "fruity": 0,
        "herbal": 0, "floral": 0, "spicy": 0, "smoky": 0, "vanilla": 0,
        "woody": 0, "minty": 0, "earthy": 0, "umami": 0,
        "body": 0, "intensity": 0,
    }
    base.update(overrides)
    return base


def _make_bottle(bid, brand, label, class_name="TestClass", family="TestFamily", **profile_kw):
    return {
        "id": bid, "brand": brand, "label": label,
        "class_name": class_name, "family_name": family,
        "on_hand": True,
        "flavor_profile": _make_profile(**profile_kw),
    }


# 5-bottle set with known clustering: A+B similar, C+D similar, E outlier
_BOTTLE_A = _make_bottle(1, "Alpha", "One", sweet=5, bitter=0, herbal=0, smoky=0, body=2, intensity=2)
_BOTTLE_B = _make_bottle(2, "Alpha", "Two", sweet=4, bitter=0, herbal=0, smoky=0, body=2, intensity=2)
_BOTTLE_C = _make_bottle(3, "Beta", "One", sweet=0, bitter=5, herbal=5, smoky=0, body=4, intensity=5)
_BOTTLE_D = _make_bottle(4, "Beta", "Two", sweet=0, bitter=4, herbal=4, smoky=0, body=4, intensity=5)
_BOTTLE_E = _make_bottle(5, "Gamma", "Solo", sweet=5, bitter=5, smoky=5, woody=5, body=5, intensity=5)

_FIVE_BOTTLES = [_BOTTLE_A, _BOTTLE_B, _BOTTLE_C, _BOTTLE_D, _BOTTLE_E]


def _build_five() -> FlavorMatrixData:
    return build_flavor_matrix(_FIVE_BOTTLES)


def _make_42_bottles():
    """Generate 42 synthetic bottles with varied profiles."""
    bottles = []
    for i in range(42):
        bottles.append(_make_bottle(
            i + 1,
            f"Brand{i}",
            f"Label{i}",
            sweet=i % 5, bitter=(i * 3) % 5,
            body=i % 4 + 1, intensity=(i * 2) % 5 + 1,
            herbal=i % 3, citrusy=(i + 1) % 4,
        ))
    return bottles


def _svg_for_42() -> str:
    data = build_flavor_matrix(_make_42_bottles())
    return render_flavor_matrix_svg(data)


def _inject_matrix(app, bottles=None):
    """Put pre-built matrix data on app.state (skipping startup event)."""
    if bottles is None:
        bottles = _FIVE_BOTTLES
    data = build_flavor_matrix(bottles)
    svg = render_flavor_matrix_svg(data)
    app.state.flavor_matrix_svg = svg
    app.state.flavor_matrix_data = data


# --- Unit tests: viridis_color ---

def test_viridis_color_thresholds():
    assert viridis_color(0.0) == "#440154"
    assert viridis_color(0.05) == "#440154"
    assert viridis_color(0.10) == "#440154"
    assert viridis_color(0.15) == "#3b528b"
    assert viridis_color(0.20) == "#3b528b"
    assert viridis_color(0.25) == "#21908d"
    assert viridis_color(0.35) == "#5dc863"
    assert viridis_color(0.50) == "#fde725"
    assert viridis_color(1.0) == "#fde725"


# --- Unit tests: build_flavor_matrix ---

def test_build_flavor_matrix_clusters_consistent_with_expectations():
    data = _build_five()
    # At least 2 clusters (A+B and C+D should cluster, E is outlier)
    assert len(data.clusters) >= 2
    assert len(data.ordered_bottles) == 5
    assert len(data.distance_matrix) == 5
    assert len(data.distance_matrix[0]) == 5
    # E should be a singleton
    assert _BOTTLE_E["id"] in data.singleton_bottle_ids
    # Inter-cluster pairs should exist
    assert len(data.inter_cluster_pairs) >= 1


# --- Page tests ---

def test_flavor_map_page_returns_200(client):
    _inject_matrix(client.app, _make_42_bottles())
    resp = client.get("/inventory/flavor-map")
    assert resp.status_code == 200
    assert "Flavor distance matrix" in resp.text


def test_flavor_map_renders_svg_with_correct_dimensions(client):
    bottles = _make_42_bottles()
    _inject_matrix(client.app, bottles)
    resp = client.get("/inventory/flavor-map")
    html = resp.text
    # 42×42 = 1764 cells, check for rect elements
    assert html.count("<rect ") == 42 * 42


def test_flavor_map_self_cells_have_distinct_color(client):
    _inject_matrix(client.app)
    resp = client.get("/inventory/flavor-map")
    # Diagonal cells use slate-800
    assert 'fill="#1e293b"' in resp.text


def test_flavor_map_cell_tooltip_format(client):
    _inject_matrix(client.app)
    resp = client.get("/inventory/flavor-map")
    # Tooltip should contain "× ... ="
    assert "\u00d7" in resp.text  # × character
    assert "<title>" in resp.text


def test_flavor_map_bottle_labels_clickable(client):
    _inject_matrix(client.app)
    resp = client.get("/inventory/flavor-map")
    # Labels should be wrapped in <a> tags linking to inventory
    assert 'xlink:href="/inventory#bottle-' in resp.text


def test_flavor_map_clusters_section_present(client):
    _inject_matrix(client.app)
    resp = client.get("/inventory/flavor-map")
    assert "Natural clusters" in resp.text
    assert "Cluster" in resp.text


def test_flavor_map_singletons_section_separate(client):
    _inject_matrix(client.app)
    resp = client.get("/inventory/flavor-map")
    # Gamma Solo should be an outlier
    assert "Outliers" in resp.text
    assert "Gamma Solo" in resp.text


def test_flavor_map_inter_cluster_pairs_top5(client):
    _inject_matrix(client.app)
    resp = client.get("/inventory/flavor-map")
    assert "Closest pairs across clusters" in resp.text
    assert "\u2194" in resp.text or "↔" in resp.text  # ↔ character


def test_flavor_map_mobile_fallback_message(client):
    _inject_matrix(client.app)
    resp = client.get("/inventory/flavor-map")
    assert "best viewed on desktop" in resp.text


def test_inventory_tabs_navigation(client):
    _inject_matrix(client.app)
    with patch(_PATCH_BOTTLES, return_value={"total": 0, "items": []}):
        resp_inv = client.get("/inventory")
    resp_map = client.get("/inventory/flavor-map")
    # Both pages have tab buttons
    assert "Collection" in resp_inv.text
    assert "Flavor map" in resp_inv.text
    assert "Collection" in resp_map.text
    assert "Flavor map" in resp_map.text


def test_flavor_map_startup_caching():
    """Startup event populates app.state.flavor_matrix_svg."""
    from fastapi.testclient import TestClient as TC
    from app.main import create_app

    bottles_resp = {"total": 5, "items": _FIVE_BOTTLES}
    mock_resp = MagicMock(status_code=200)

    with patch("httpx.get", return_value=mock_resp), \
         patch("app.client.fetch_all_bottles", return_value=bottles_resp):
        app = create_app()
        # TestClient.__enter__ triggers startup events
        with TC(app) as tc:
            assert app.state.flavor_matrix_svg is not None
            assert "<svg" in app.state.flavor_matrix_svg
            assert app.state.flavor_matrix_data is not None


def test_flavor_map_unavailable_when_backend_down_at_startup(client):
    """When backend was down at startup, show friendly error."""
    client.app.state.flavor_matrix_svg = None
    client.app.state.flavor_matrix_data = None
    resp = client.get("/inventory/flavor-map")
    assert resp.status_code == 200
    assert "not yet available" in resp.text


def test_flavor_map_htmx_tab_swap(client):
    """HTMX tab swap returns partial content."""
    _inject_matrix(client.app)
    resp = client.get(
        "/inventory/flavor-map",
        headers={"HX-Request": "true", "HX-Target": "tab-content"},
    )
    assert resp.status_code == 200
    assert "<html" not in resp.text
    assert "Flavor distance matrix" in resp.text
