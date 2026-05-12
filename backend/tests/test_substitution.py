"""Tests for similar-bottles, substitutions, and substitution-trace endpoints."""

import pytest

# ---------------------------------------------------------------------------
# flavor profiles with known relative distances
# ---------------------------------------------------------------------------

_PROFILE_GIN = {
    "sweet": 1, "bitter": 2, "sour": 0, "citrusy": 4, "fruity": 1,
    "herbal": 3, "floral": 2, "spicy": 1, "smoky": 0, "vanilla": 0,
    "woody": 0, "minty": 0, "earthy": 0, "umami": 0,
    "body": 2, "intensity": 3,
}

_PROFILE_SIMILAR_GIN = {
    "sweet": 1, "bitter": 2, "sour": 0, "citrusy": 5, "fruity": 1,
    "herbal": 4, "floral": 3, "spicy": 2, "smoky": 0, "vanilla": 0,
    "woody": 1, "minty": 0, "earthy": 0, "umami": 0,
    "body": 3, "intensity": 4,
}

_PROFILE_VODKA = {
    "sweet": 0, "bitter": 0, "sour": 0, "citrusy": 0, "fruity": 0,
    "herbal": 0, "floral": 0, "spicy": 0, "smoky": 0, "vanilla": 1,
    "woody": 0, "minty": 0, "earthy": 0, "umami": 0,
    "body": 1, "intensity": 2,
}

_PROFILE_CAMPARI = {
    "sweet": 2, "bitter": 5, "sour": 1, "citrusy": 3, "fruity": 2,
    "herbal": 2, "floral": 0, "spicy": 1, "smoky": 0, "vanilla": 0,
    "woody": 0, "minty": 0, "earthy": 0, "umami": 0,
    "body": 3, "intensity": 4,
}

_PROFILE_APEROL = {
    "sweet": 4, "bitter": 3, "sour": 1, "citrusy": 3, "fruity": 3,
    "herbal": 1, "floral": 0, "spicy": 0, "smoky": 0, "vanilla": 0,
    "woody": 0, "minty": 0, "earthy": 0, "umami": 0,
    "body": 2, "intensity": 2,
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make(client, class_name, brand, label, profile, on_hand=True):
    resp = client.post("/api/bottles", json={
        "class_name": class_name,
        "brand": brand,
        "label": label,
        "abv": 40.0,
        "on_hand": on_hand,
        "flavor_profile": profile,
        "notes": None,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _cleanup(client, ids):
    for bid in ids:
        client.delete(f"/api/bottles/{bid}")


def _recipe_id(client, name):
    resp = client.get(f"/api/recipes/by-name?name={name}")
    assert resp.status_code == 200, f"Recipe '{name}' not found"
    return resp.json()["id"]


# ===================================================================
# similar-bottles
# ===================================================================

def test_similar_bottles_returns_pivot_excluded(client):
    ids = [
        _make(client, "TestGin", "SimPivot", "A", _PROFILE_GIN),
        _make(client, "TestVodka", "SimOther", "B", _PROFILE_VODKA),
    ]
    try:
        resp = client.get(f"/api/flavor/similar-bottles?bottle_id={ids[0]}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["pivot"]["id"] == ids[0]
        result_ids = {r["bottle"]["id"] for r in data["results"]}
        assert ids[0] not in result_ids
    finally:
        _cleanup(client, ids)


def test_similar_bottles_orders_by_distance_asc(client):
    ids = [
        _make(client, "TestGin", "SimPiv", "P", _PROFILE_GIN),
        _make(client, "TestLondonDryGin", "SimClose", "C", _PROFILE_SIMILAR_GIN),
        _make(client, "TestVodka", "SimFar", "F", _PROFILE_VODKA),
    ]
    try:
        resp = client.get(f"/api/flavor/similar-bottles?bottle_id={ids[0]}")
        data = resp.json()
        distances = [r["distance"] for r in data["results"]]
        assert distances == sorted(distances)
        # Similar gin should be closer than neutral vodka
        assert data["results"][0]["bottle"]["id"] == ids[1]
    finally:
        _cleanup(client, ids)


def test_similar_bottles_respects_max_distance(client):
    ids = [
        _make(client, "TestGin", "SimMD_P", "P", _PROFILE_GIN),
        _make(client, "TestLondonDryGin", "SimMD_C", "C", _PROFILE_SIMILAR_GIN),
        _make(client, "TestVodka", "SimMD_F", "F", _PROFILE_VODKA),
    ]
    try:
        # Very tight max_distance — should exclude the far vodka
        resp = client.get(
            f"/api/flavor/similar-bottles?bottle_id={ids[0]}&max_distance=0.15"
        )
        data = resp.json()
        result_ids = {r["bottle"]["id"] for r in data["results"]}
        assert ids[2] not in result_ids  # vodka too far
    finally:
        _cleanup(client, ids)


def test_similar_bottles_same_family_only(client):
    ids = [
        _make(client, "TestGin", "SimFam_P", "P", _PROFILE_GIN),
        _make(client, "TestLondonDryGin", "SimFam_S", "S", _PROFILE_SIMILAR_GIN),
        _make(client, "TestCampari", "SimFam_X", "X", _PROFILE_CAMPARI),
    ]
    try:
        resp = client.get(
            f"/api/flavor/similar-bottles?bottle_id={ids[0]}&same_family_only=true"
        )
        data = resp.json()
        result_ids = {r["bottle"]["id"] for r in data["results"]}
        # LondonDryGin same family (TestGinFamily), Campari different
        assert ids[1] in result_ids
        assert ids[2] not in result_ids
        for r in data["results"]:
            assert r["same_family"] is True
    finally:
        _cleanup(client, ids)


def test_similar_bottles_404_for_missing_bottle(client):
    resp = client.get("/api/flavor/similar-bottles?bottle_id=99999")
    assert resp.status_code == 404


def test_similar_bottles_has_dimension_info(client):
    ids = [
        _make(client, "TestGin", "SimDim_P", "P", _PROFILE_GIN),
        _make(client, "TestLondonDryGin", "SimDim_S", "S", _PROFILE_SIMILAR_GIN),
    ]
    try:
        resp = client.get(f"/api/flavor/similar-bottles?bottle_id={ids[0]}")
        data = resp.json()
        r = data["results"][0]
        assert len(r["top_shared_dimensions"]) == 4
        assert len(r["top_differing_dimensions"]) <= 3
    finally:
        _cleanup(client, ids)


# ===================================================================
# substitutions
# ===================================================================

def test_substitutions_excludes_anti_doppione(client):
    """For Negroni (TestGin + TestVodka), TestGin bottle must not appear
    as substitute for TestVodka since TestGin is already in the recipe."""
    ids = [
        _make(client, "TestGin", "SubAD_Gin", "G", _PROFILE_GIN),
        _make(client, "TestLondonDryGin", "SubAD_LDG", "L", _PROFILE_SIMILAR_GIN),
        # TestVodka off-hand — makes Negroni not feasible
        _make(client, "TestVodka", "SubAD_Vod", "V", _PROFILE_VODKA, on_hand=False),
    ]
    try:
        rid = _recipe_id(client, "Test Negroni")
        resp = client.get(f"/api/recipes/{rid}/substitutions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_feasibility"]["can_make"] is False

        # Find the unsatisfied ingredient (TestVodka)
        unsatisfied = [
            a for a in data["ingredients_analysis"] if not a["is_satisfied"]
        ]
        assert len(unsatisfied) >= 1
        vodka_analysis = next(
            a for a in unsatisfied if a["class_name"] == "TestVodka"
        )
        assert "TestGin" in vodka_analysis["anti_doppione_classes"]

        # TestGin bottle must NOT appear in substitutions
        all_sub_ids = set()
        for tier in ("strict", "loose"):
            for s in vodka_analysis["substitutions"][tier]:
                all_sub_ids.add(s["bottle"]["id"])
        assert ids[0] not in all_sub_ids  # gin excluded as anti-doppione
    finally:
        _cleanup(client, ids)


def test_substitutions_returns_strict_tier_for_same_family(client):
    """For Americano (TestCampari + commodity), if TestCampari is missing
    but TestAperol (same family TestAperitif) is on hand, it's tier=strict."""
    ids = [
        _make(client, "TestAperol", "SubST_Ap", "A", _PROFILE_APEROL),
        # TestCampari off-hand
        _make(client, "TestCampari", "SubST_Cam", "C", _PROFILE_CAMPARI, on_hand=False),
    ]
    try:
        rid = _recipe_id(client, "Test Americano")
        resp = client.get(
            f"/api/recipes/{rid}/substitutions?strict_threshold=0.50"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_feasibility"]["can_make"] is False

        campari_analysis = next(
            a for a in data["ingredients_analysis"]
            if a["class_name"] == "TestCampari"
        )
        strict_subs = campari_analysis["substitutions"]["strict"]
        assert len(strict_subs) >= 1
        assert strict_subs[0]["tier"] == "strict"
        assert strict_subs[0]["bottle"]["class_name"] == "TestAperol"
    finally:
        _cleanup(client, ids)


def test_substitutions_returns_loose_tier_for_cross_family(client):
    """A bottle in a different family with low distance appears as loose."""
    ids = [
        _make(client, "TestGin", "SubLO_Gin", "G", _PROFILE_GIN),
        # TestCampari off-hand
        _make(client, "TestCampari", "SubLO_Cam", "C", _PROFILE_CAMPARI, on_hand=False),
    ]
    try:
        rid = _recipe_id(client, "Test Americano")
        resp = client.get(
            f"/api/recipes/{rid}/substitutions?loose_threshold=0.50"
        )
        assert resp.status_code == 200
        data = resp.json()

        campari_analysis = next(
            a for a in data["ingredients_analysis"]
            if a["class_name"] == "TestCampari"
        )
        loose_subs = campari_analysis["substitutions"]["loose"]
        assert len(loose_subs) >= 1
        assert loose_subs[0]["tier"] == "loose"
        # TestGin is in TestGinFamily, TestCampari in TestAperitif → cross-family
        assert loose_subs[0]["bottle"]["class_name"] == "TestGin"
    finally:
        _cleanup(client, ids)


def test_substitutions_satisfied_ingredient_skipped_by_default(client):
    """Fully feasible recipe → empty ingredients_analysis."""
    ids = [
        _make(client, "TestCampari", "SubSat_C", "C", _PROFILE_CAMPARI),
    ]
    try:
        rid = _recipe_id(client, "Test Americano")
        resp = client.get(f"/api/recipes/{rid}/substitutions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_feasibility"]["can_make"] is True
        assert len(data["ingredients_analysis"]) == 0
    finally:
        _cleanup(client, ids)


def test_substitutions_satisfied_ingredient_included_when_flag_true(client):
    """With include_satisfied=true, satisfied ingredients appear."""
    ids = [
        _make(client, "TestCampari", "SubIncl_C", "C", _PROFILE_CAMPARI),
    ]
    try:
        rid = _recipe_id(client, "Test Americano")
        resp = client.get(
            f"/api/recipes/{rid}/substitutions?include_satisfied=true"
        )
        assert resp.status_code == 200
        data = resp.json()
        satisfied = [
            a for a in data["ingredients_analysis"] if a["is_satisfied"]
        ]
        assert len(satisfied) >= 1
        assert satisfied[0]["class_name"] == "TestCampari"
        assert len(satisfied[0]["satisfied_by_bottles"]) >= 1
    finally:
        _cleanup(client, ids)


def test_substitutions_class_without_bottles_aggregates_siblings(client):
    """For Aperol Spritz (needs TestAperol), if no TestAperol bottles exist
    but a TestCampari sibling bottle does, pivot aggregates from sibling."""
    ids = [
        # Only TestCampari on hand; no TestAperol bottles at all
        _make(client, "TestCampari", "SubSib_C", "C", _PROFILE_CAMPARI),
    ]
    try:
        rid = _recipe_id(client, "Test Aperol Spritz")
        resp = client.get(
            f"/api/recipes/{rid}/substitutions?strict_threshold=0.50&loose_threshold=0.50"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_feasibility"]["can_make"] is False

        aperol_analysis = next(
            a for a in data["ingredients_analysis"]
            if a["class_name"] == "TestAperol"
        )
        assert not aperol_analysis["is_satisfied"]
        # TestCampari should appear as strict substitute (same family TestAperitif)
        # The pivot was aggregated from sibling (TestCampari)
        strict = aperol_analysis["substitutions"]["strict"]
        assert len(strict) >= 1
        assert strict[0]["bottle"]["class_name"] == "TestCampari"
    finally:
        _cleanup(client, ids)


def test_substitutions_alternative_group_handled(client):
    """Boulevardier has alt_group (TestGin OR TestVodka) + TestCampari.
    With only TestAperol on hand, neither alt member is satisfied →
    substitutions for the representative + note."""
    ids = [
        _make(client, "TestAperol", "SubAlt_Ap", "A", _PROFILE_APEROL),
        # TestCampari off-hand
        _make(client, "TestCampari", "SubAlt_Cam", "C", _PROFILE_CAMPARI, on_hand=False),
    ]
    try:
        rid = _recipe_id(client, "Test Boulevardier")
        resp = client.get(
            f"/api/recipes/{rid}/substitutions?strict_threshold=0.50&loose_threshold=0.50"
        )
        assert resp.status_code == 200
        data = resp.json()

        # Find the alt-group ingredient
        alt_entries = [
            a for a in data["ingredients_analysis"]
            if a.get("note") and "alternative group" in a["note"]
        ]
        assert len(alt_entries) >= 1
        assert "TestGin" in alt_entries[0]["note"] or "TestVodka" in alt_entries[0]["note"]
    finally:
        _cleanup(client, ids)


def test_substitutions_404_for_missing_recipe(client):
    resp = client.get("/api/recipes/99999/substitutions")
    assert resp.status_code == 404


# ===================================================================
# substitution-trace
# ===================================================================

def test_substitution_trace_returns_detailed_breakdown(client):
    """Trace endpoint returns pivot_profile and per-bottle detail."""
    ids = [
        _make(client, "TestGin", "Trace_Gin", "G", _PROFILE_GIN),
        _make(client, "TestVodka", "Trace_Vod", "V", _PROFILE_VODKA, on_hand=False),
    ]
    try:
        rid = _recipe_id(client, "Test Negroni")
        # First get recipe_ingredient_id from substitutions
        sub_resp = client.get(f"/api/recipes/{rid}/substitutions")
        assert sub_resp.status_code == 200
        sub_data = sub_resp.json()
        unsatisfied = [
            a for a in sub_data["ingredients_analysis"] if not a["is_satisfied"]
        ]
        assert len(unsatisfied) >= 1
        ri_id = unsatisfied[0]["recipe_ingredient_id"]

        # Now call trace
        resp = client.get(
            f"/api/flavor/substitution-trace?recipe_id={rid}"
            f"&recipe_ingredient_id={ri_id}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["recipe_ingredient_id"] == ri_id
        assert data["pivot_profile"] is not None
        assert "pivot_source" in data
        assert isinstance(data["on_hand_bottles"], list)
        # Each entry has distance and included/exclusion_reason
        for entry in data["on_hand_bottles"]:
            assert "distance" in entry
            assert "included" in entry
    finally:
        _cleanup(client, ids)


def test_substitution_trace_404_for_missing(client):
    resp = client.get(
        "/api/flavor/substitution-trace?recipe_id=99999&recipe_ingredient_id=1"
    )
    assert resp.status_code == 404
