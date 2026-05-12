import pytest

from app.services.flavor import (
    DIMS_GUSTATIVE,
    DIMS_STRUCTURAL,
    aggregate_class_profile,
    flavor_breakdown,
    flavor_distance,
)

_ALL_DIMS = DIMS_GUSTATIVE + DIMS_STRUCTURAL

_FLAVOR_A = {
    "sweet": 2, "bitter": 4, "sour": 1, "citrusy": 5, "fruity": 2,
    "herbal": 3, "floral": 3, "spicy": 1, "smoky": 0, "vanilla": 1,
    "woody": 2, "minty": 0, "earthy": 1, "umami": 0,
    "body": 3, "intensity": 4,
}

_FLAVOR_B = {
    "sweet": 4, "bitter": 1, "sour": 3, "citrusy": 2, "fruity": 4,
    "herbal": 1, "floral": 5, "spicy": 0, "smoky": 2, "vanilla": 3,
    "woody": 0, "minty": 2, "earthy": 0, "umami": 1,
    "body": 2, "intensity": 2,
}


# -- unit tests: flavor_distance -------------------------------------------

def test_flavor_distance_identical_profiles_returns_zero():
    p = {dim: 3 for dim in _ALL_DIMS}
    assert flavor_distance(p, p) == 0.0


def test_flavor_distance_maximally_different_returns_one():
    p_zero = {dim: 0 for dim in _ALL_DIMS}
    p_five = {dim: 5 for dim in _ALL_DIMS}
    assert abs(flavor_distance(p_zero, p_five) - 1.0) < 1e-9


def test_flavor_distance_is_symmetric():
    assert flavor_distance(_FLAVOR_A, _FLAVOR_B) == flavor_distance(_FLAVOR_B, _FLAVOR_A)


def test_flavor_distance_respects_weights():
    # A has gustative differences only; B has structural differences only
    p_a = {dim: 5 if dim in DIMS_GUSTATIVE else 0 for dim in _ALL_DIMS}
    p_b = {dim: 0 for dim in _ALL_DIMS}  # zero everywhere
    p_c = {dim: 5 if dim in DIMS_STRUCTURAL else 0 for dim in _ALL_DIMS}

    d_gustative_heavy = flavor_distance(p_a, p_b, gustative_weight=0.9, structural_weight=0.1)
    d_structural_heavy = flavor_distance(p_a, p_b, gustative_weight=0.1, structural_weight=0.9)
    # p_a vs p_b: gustative distance is 1.0, structural is 0.0
    # gustative_heavy → 0.9*1.0 + 0.1*0.0 = 0.9
    # structural_heavy → 0.1*1.0 + 0.9*0.0 = 0.1
    assert d_gustative_heavy > d_structural_heavy

    d2_gustative_heavy = flavor_distance(p_c, p_b, gustative_weight=0.9, structural_weight=0.1)
    d2_structural_heavy = flavor_distance(p_c, p_b, gustative_weight=0.1, structural_weight=0.9)
    # p_c vs p_b: gustative distance is 0.0, structural is 1.0
    assert d2_structural_heavy > d2_gustative_heavy


def test_flavor_distance_rejects_missing_keys():
    p_incomplete = {"sweet": 3}
    p_full = {dim: 3 for dim in _ALL_DIMS}
    with pytest.raises(ValueError, match="missing keys"):
        flavor_distance(p_incomplete, p_full)


def test_flavor_distance_rejects_extra_keys():
    p_extra = {dim: 3 for dim in _ALL_DIMS}
    p_extra["bogus"] = 1
    p_full = {dim: 3 for dim in _ALL_DIMS}
    with pytest.raises(ValueError, match="extra keys"):
        flavor_distance(p_extra, p_full)


def test_flavor_distance_rejects_invalid_weights():
    p = {dim: 3 for dim in _ALL_DIMS}
    with pytest.raises(ValueError, match="must sum to 1"):
        flavor_distance(p, p, gustative_weight=0.5, structural_weight=0.3)


# -- unit tests: flavor_breakdown ------------------------------------------

def test_flavor_breakdown_orders_by_abs_delta():
    # dolce=5→0 (delta 5), amaro=0→4 (delta 4), rest equal
    p_a = {dim: 0 for dim in _ALL_DIMS}
    p_a["sweet"] = 5
    p_b = {dim: 0 for dim in _ALL_DIMS}
    p_b["bitter"] = 4

    result = flavor_breakdown(p_a, p_b)
    deltas = [pd.abs_delta for pd in result.per_dimension]
    assert deltas == sorted(deltas, reverse=True)
    assert result.per_dimension[0].dimension == "sweet"
    assert result.per_dimension[0].abs_delta == 5
    assert result.per_dimension[1].dimension == "bitter"
    assert result.per_dimension[1].abs_delta == 4


def test_flavor_breakdown_total_matches_distance():
    result = flavor_breakdown(_FLAVOR_A, _FLAVOR_B)
    expected = flavor_distance(_FLAVOR_A, _FLAVOR_B)
    assert abs(result.total_distance - expected) < 1e-12


def test_flavor_breakdown_per_dimension_has_16_entries():
    result = flavor_breakdown(_FLAVOR_A, _FLAVOR_B)
    assert len(result.per_dimension) == 16


# -- unit tests: aggregate_class_profile -----------------------------------

def test_aggregate_class_profile_uses_median():
    profiles = [
        {dim: 0 for dim in _ALL_DIMS},
        {dim: 2 for dim in _ALL_DIMS},
        {dim: 5 for dim in _ALL_DIMS},
    ]
    result = aggregate_class_profile(profiles)
    assert all(v == 2 for v in result.values())


def test_aggregate_class_profile_single_profile():
    p = {dim: 3 for dim in _ALL_DIMS}
    assert aggregate_class_profile([p]) == p


def test_aggregate_class_profile_even_count_rounds():
    # Median of [1, 3] = 2.0 → rounds to 2
    profiles = [
        {dim: 1 for dim in _ALL_DIMS},
        {dim: 3 for dim in _ALL_DIMS},
    ]
    result = aggregate_class_profile(profiles)
    assert all(v == 2 for v in result.values())


def test_aggregate_class_profile_empty_raises():
    with pytest.raises(ValueError):
        aggregate_class_profile([])


# -- endpoint tests ---------------------------------------------------------

_FLAVOR_EP = {
    "sweet": 1, "bitter": 0, "sour": 1, "citrusy": 2,
    "fruity": 1, "herbal": 3, "floral": 2, "spicy": 1,
    "smoky": 0, "vanilla": 0, "woody": 0, "minty": 0,
    "earthy": 0, "umami": 0, "body": 2, "intensity": 4,
}

_FLAVOR_EP2 = {
    "sweet": 4, "bitter": 3, "sour": 0, "citrusy": 0,
    "fruity": 5, "herbal": 0, "floral": 1, "spicy": 2,
    "smoky": 3, "vanilla": 4, "woody": 1, "minty": 0,
    "earthy": 2, "umami": 1, "body": 4, "intensity": 3,
}


def _create_bottle(client, flavor, brand="FlavorTest", label="FT1",
                   class_name="TestGin"):
    body = {
        "class_name": class_name,
        "brand": brand,
        "label": label,
        "abv": 40.0,
        "on_hand": True,
        "flavor_profile": flavor,
        "notes": None,
    }
    return client.post("/api/bottles", json=body)


def test_distance_endpoint_returns_valid_breakdown(client):
    r1 = _create_bottle(client, _FLAVOR_EP, brand="FD_A", label="FDA1")
    r2 = _create_bottle(client, _FLAVOR_EP2, brand="FD_B", label="FDB1")
    id1, id2 = r1.json()["id"], r2.json()["id"]

    resp = client.get(f"/api/flavor/distance?bottle_a={id1}&bottle_b={id2}")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_distance" in data
    assert 0 <= data["total_distance"] <= 1
    assert len(data["per_dimension"]) == 16
    assert data["bottle_a"]["id"] == id1
    assert data["bottle_b"]["id"] == id2
    assert data["bottle_a"]["brand"] == "FD_A"

    client.delete(f"/api/bottles/{id1}")
    client.delete(f"/api/bottles/{id2}")


def test_distance_endpoint_404_for_missing_bottle(client):
    r1 = _create_bottle(client, _FLAVOR_EP, brand="FD_404", label="FD404")
    id1 = r1.json()["id"]

    resp = client.get(f"/api/flavor/distance?bottle_a=99999&bottle_b={id1}")
    assert resp.status_code == 404

    client.delete(f"/api/bottles/{id1}")


def test_distance_endpoint_422_for_invalid_weights(client):
    r1 = _create_bottle(client, _FLAVOR_EP, brand="FD_W1", label="FDW1")
    r2 = _create_bottle(client, _FLAVOR_EP, brand="FD_W2", label="FDW2")
    id1, id2 = r1.json()["id"], r2.json()["id"]

    resp = client.get(
        f"/api/flavor/distance?bottle_a={id1}&bottle_b={id2}"
        "&gustative_weight=0.5&structural_weight=0.6"
    )
    assert resp.status_code == 422

    client.delete(f"/api/bottles/{id1}")
    client.delete(f"/api/bottles/{id2}")
