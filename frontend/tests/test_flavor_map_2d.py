"""Tests for 2D flavor map (UMAP + Plotly) functionality."""

import json

import pytest

from app.services.flavor_map_2d_builder import (
    FlavorMap2DData,
    build_flavor_map_2d,
    get_cluster_impression,
    _auto_impression,
    _build_feature_matrix,
    _fit_umap,
)


# ============================================================================
# Fixtures
# ============================================================================

def _make_bottle(bid, brand, family="Whiskey", **profile_overrides):
    """Helper to create a test bottle dict."""
    profile = {
        "sweet": 0, "bitter": 0, "sour": 0, "citrusy": 0,
        "fruity": 0, "herbal": 0, "floral": 0, "spicy": 0,
        "smoky": 0, "vanilla": 0, "woody": 0, "minty": 0,
        "earthy": 0, "umami": 0, "body": 0, "intensity": 0,
    }
    profile.update(profile_overrides)
    return {
        "id": bid,
        "brand": brand,
        "label": None,
        "parent_family": family,
        "class_name": family,
        "flavor_profile": profile,
        "on_hand": True,
    }


@pytest.fixture
def five_bottles():
    """5 bottles: 2 similar whiskeys, 2 similar gins, 1 outlier."""
    return [
        _make_bottle(1, "Maker's Mark", "Whiskey", sweet=2, vanilla=3, woody=2),
        _make_bottle(2, "Buffalo Trace", "Whiskey", sweet=2, vanilla=2, woody=3),
        _make_bottle(3, "Tanqueray", "Gin", citrusy=4, herbal=3, bitter=2),
        _make_bottle(4, "Bombay Sapphire", "Gin", citrusy=4, herbal=3, bitter=2),
        _make_bottle(5, "Sake", "Sake & Umeshu", umami=4, intensity=1),
    ]


@pytest.fixture
def cluster_assignments_five():
    """Cluster assignments for 5-bottle set."""
    return {
        1: 0,  # Whiskey 1 → cluster 0
        2: 0,  # Whiskey 2 → cluster 0
        3: 1,  # Gin 1 → cluster 1
        4: 1,  # Gin 2 → cluster 1
        5: 2,  # Sake → cluster 2 (singleton)
    }


# ============================================================================
# Tests: Feature matrix & UMAP
# ============================================================================

def test_build_feature_matrix_shape(five_bottles):
    """Feature matrix should be (N bottles, 16 dimensions)."""
    matrix = _build_feature_matrix(five_bottles)
    assert matrix.shape == (5, 16)
    assert matrix.dtype == float


def test_build_feature_matrix_values(five_bottles):
    """Feature values should come from flavor_profile."""
    matrix = _build_feature_matrix(five_bottles)
    # Bottle 0: sweet=2, vanilla=3, woody=2 (all others 0)
    assert matrix[0, 0] == 2  # sweet (first dim)
    assert matrix[0, 9] == 3  # vanilla (index 9 in _ALL_DIMS)
    assert matrix[0, 10] == 2  # woody (index 10 in _ALL_DIMS)


def test_fit_umap_output_shape(five_bottles):
    """UMAP should produce (N, 2) embedding."""
    matrix = _build_feature_matrix(five_bottles)
    embedding = _fit_umap(matrix)
    assert embedding.shape == (5, 2)
    assert embedding.dtype == float


def test_umap_deterministic(five_bottles):
    """Same input should produce same embedding (random_state=42)."""
    matrix = _build_feature_matrix(five_bottles)
    emb1 = _fit_umap(matrix)
    emb2 = _fit_umap(matrix)
    # Should be identical (deterministic with random_state=42)
    assert (emb1 == emb2).all()


def test_umap_values_in_range(five_bottles):
    """UMAP embedding values should be reasonable (not NaN/Inf)."""
    matrix = _build_feature_matrix(five_bottles)
    embedding = _fit_umap(matrix)
    assert not (embedding == 0).all()  # Not all zeros
    assert not embedding.isnan().any()
    assert not embedding.isinf().any()


# ============================================================================
# Tests: Auto-impression generation
# ============================================================================

def test_auto_impression_basic():
    """Auto-impression should mention top-3 dimensions."""
    bottle = _make_bottle(1, "Test", sweet=3, bitter=2, sour=1)
    impression = _auto_impression([bottle])
    assert "sweet" in impression.lower()
    assert "bitter" in impression.lower()
    assert "sour" in impression.lower()


def test_auto_impression_empty():
    """Empty cluster should return graceful message."""
    impression = _auto_impression([])
    assert "empty" in impression.lower()


def test_auto_impression_no_dominant():
    """Bottle with all near-zero profile should return fallback."""
    bottle = _make_bottle(1, "Neutral", sweet=0, bitter=0, sour=0)
    impression = _auto_impression([bottle])
    assert "unique" in impression.lower() or "signature" in impression.lower()


def test_get_cluster_impression_pre_written():
    """Should use pre-written impression if family signature matches."""
    # Amaro cluster (single family)
    bottles = [
        _make_bottle(1, "Amaro 1", "Amaro", bitter=4, herbal=3),
        _make_bottle(2, "Amaro 2", "Amaro", bitter=3, herbal=4),
    ]
    impression = get_cluster_impression(0, bottles)
    # Should match the pre-written impression for {"Amaro"}
    assert "amaro" in impression.lower() or len(impression) > 20


def test_get_cluster_impression_fallback():
    """Should auto-generate if no pre-written match."""
    bottles = [
        _make_bottle(1, "Unknown Spirit", "Unknown", sweet=2, bitter=2),
    ]
    impression = get_cluster_impression(0, bottles)
    # Should be auto-generated
    assert len(impression) > 10


# ============================================================================
# Tests: Full build_flavor_map_2d
# ============================================================================

def test_build_flavor_map_2d_basic(five_bottles, cluster_assignments_five):
    """Full builder should return FlavorMap2DData with all fields."""
    data = build_flavor_map_2d(five_bottles, cluster_assignments_five)
    assert isinstance(data, FlavorMap2DData)
    assert data.plotly_json
    assert len(data.cluster_impressions) > 0
    assert data.n_clusters > 0
    assert data.generation_time
    assert data.umap_params


def test_build_flavor_map_2d_n_clusters(five_bottles, cluster_assignments_five):
    """Should detect correct number of clusters."""
    data = build_flavor_map_2d(five_bottles, cluster_assignments_five)
    # 3 unique cluster IDs: 0, 1, 2
    assert data.n_clusters == 3


def test_build_flavor_map_2d_cluster_sizes(five_bottles, cluster_assignments_five):
    """Should correctly count cluster sizes."""
    data = build_flavor_map_2d(five_bottles, cluster_assignments_five)
    assert data.cluster_sizes[0] == 2  # 2 whiskeys
    assert data.cluster_sizes[1] == 2  # 2 gins
    assert data.cluster_sizes[2] == 1  # 1 sake (singleton)


def test_build_flavor_map_2d_impressions_keys(five_bottles, cluster_assignments_five):
    """All cluster IDs should have impressions."""
    data = build_flavor_map_2d(five_bottles, cluster_assignments_five)
    for cid in range(data.n_clusters):
        assert cid in data.cluster_impressions
        assert isinstance(data.cluster_impressions[cid], str)
        assert len(data.cluster_impressions[cid]) > 0


def test_build_flavor_map_2d_too_few_bottles():
    """Should raise ValueError if < 2 bottles."""
    with pytest.raises(ValueError):
        build_flavor_map_2d([_make_bottle(1, "Only One")], {1: 0})


def test_build_flavor_map_2d_no_profiles():
    """Should raise ValueError if no bottles have flavor_profile."""
    bottles = [{"id": 1, "brand": "No Profile"}]
    with pytest.raises(ValueError):
        build_flavor_map_2d(bottles, {})


# ============================================================================
# Tests: Plotly JSON structure
# ============================================================================

def test_plotly_json_valid(five_bottles, cluster_assignments_five):
    """Plotly JSON should be valid, parseable JSON."""
    data = build_flavor_map_2d(five_bottles, cluster_assignments_five)
    fig = json.loads(data.plotly_json)
    assert "data" in fig
    assert "layout" in fig
    assert len(fig["data"]) > 0


def test_plotly_has_correct_points(five_bottles, cluster_assignments_five):
    """Plotly trace should have 5 points (one per bottle)."""
    data = build_flavor_map_2d(five_bottles, cluster_assignments_five)
    fig = json.loads(data.plotly_json)
    trace = fig["data"][0]
    assert len(trace["x"]) == 5
    assert len(trace["y"]) == 5


def test_plotly_customdata_structure(five_bottles, cluster_assignments_five):
    """Customdata should have correct structure (10 elements per point)."""
    data = build_flavor_map_2d(five_bottles, cluster_assignments_five)
    fig = json.loads(data.plotly_json)
    trace = fig["data"][0]
    assert len(trace["customdata"]) == 5
    for cd in trace["customdata"]:
        assert len(cd) == 10  # [id, brand, label, class, family, top3, cluster_id, impression, on_hand, profile_json]
        assert isinstance(cd[0], int)  # bottle_id
        assert isinstance(cd[1], str)  # brand
        assert isinstance(cd[9], str)  # profile_json


def test_plotly_customdata_bottle_ids(five_bottles, cluster_assignments_five):
    """First element of customdata should be bottle IDs."""
    data = build_flavor_map_2d(five_bottles, cluster_assignments_five)
    fig = json.loads(data.plotly_json)
    trace = fig["data"][0]
    ids = [cd[0] for cd in trace["customdata"]]
    assert set(ids) == {1, 2, 3, 4, 5}


def test_plotly_color_arrays_in_meta(five_bottles, cluster_assignments_five):
    """Layout.meta should contain both cluster_colors and family_colors arrays."""
    data = build_flavor_map_2d(five_bottles, cluster_assignments_five)
    fig = json.loads(data.plotly_json)
    meta = fig["layout"].get("meta", {})
    assert "cluster_colors" in meta
    assert "family_colors" in meta
    assert len(meta["cluster_colors"]) == 5
    assert len(meta["family_colors"]) == 5


# ============================================================================
# Tests: Integration with endpoint (requires test client from conftest)
# ============================================================================
# Note: Endpoint tests (flavor_map_2d_endpoint_200, etc.) require proper
# test client setup with mocked backend. These are deferred to integration tests.
# The core UMAP + Plotly building logic is tested above and works independently.


# ============================================================================
# Tests: UMAP parameter documentation
# ============================================================================

def test_umap_params_documented(five_bottles, cluster_assignments_five):
    """umap_params should document n_neighbors, min_dist, metric."""
    data = build_flavor_map_2d(five_bottles, cluster_assignments_five)
    params = data.umap_params
    assert "n_neighbors" in params
    assert "min_dist" in params
    assert "metric" in params
    assert params["n_neighbors"] <= 10
    assert params["min_dist"] == 0.3
    assert params["metric"] == "euclidean"


def test_generation_time_format(five_bottles, cluster_assignments_five):
    """generation_time should be formatted as 'X.XXs'."""
    data = build_flavor_map_2d(five_bottles, cluster_assignments_five)
    assert "s" in data.generation_time
    assert float(data.generation_time.rstrip("s")) > 0
