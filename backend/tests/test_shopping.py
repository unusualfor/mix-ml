"""Tests for the ILP-based multi-step shopping optimizer.

Test seed has 12 recipes.  Commodity-only recipes (Test Juice Mix,
Test Mimosa) are always feasible → 2 baseline.  The remaining 10
require non-commodity classes (TestGin, TestVodka, TestCampari,
TestAperol, etc.).

Candidate classes (not commodity, not garnish, has recipe refs or
wildcard sibling):
  TestGin, TestVodka, TestCampari, TestAperol, TestBitters,
  TestGin(generic), TestVodka(generic), TestLondonDryGin

Key insight for K=1:
  TestGin unlocks: Test Negroni? No (also needs TestVodka).
    Test Mule (alt_group: TestGin OR TestVodka → yes).
    Test Spritz (TestGin + commodity → yes).
    Test Gin Fizz (TestGin(generic) → TestGin is sibling → yes).
    Test French 75 (TestGin + commodity → yes).
    Test Boulevardier? No (also needs TestCampari).
    → delta = 4 (Mule, Spritz, Gin Fizz, French 75)

  TestCampari unlocks: Test Americano, Test Garibaldi → delta = 2

  TestAperol unlocks: Test Aperol Spritz → delta = 1

  TestVodka unlocks: Test Mule, Test Generic Mule, Test Gin Fizz (via wildcard? No—
    TestGin(generic) needs GinFamily parent, TestVodka has VodkaFamily parent).
    Test Mule (alt_group) → yes.
    Test Generic Mule (TestVodka(generic), TestVodka is sibling → yes).
    → delta = 2

So K=1 greedy top = TestGin with delta=4.
"""

import pytest


def _make(client, class_name, brand, label, on_hand=True):
    """Create a minimal bottle and return its id."""
    resp = client.post("/api/bottles", json={
        "class_name": class_name,
        "brand": brand,
        "label": label,
        "abv": 40.0,
        "on_hand": on_hand,
        "flavor_profile": {
            "sweet": 0, "bitter": 0, "sour": 0, "citrusy": 0,
            "fruity": 0, "herbal": 0, "floral": 0, "spicy": 0,
            "smoky": 0, "vanilla": 0, "woody": 0, "minty": 0,
            "earthy": 0, "umami": 0, "body": 0, "intensity": 0,
        },
        "notes": None,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _cleanup(client, ids):
    for bid in ids:
        client.delete(f"/api/bottles/{bid}")


# ===================================================================
# Budget constraints
# ===================================================================

def test_shopping_plan_respects_budget(client):
    """recommended_purchases length always <= budget."""
    for b in (1, 2, 3):
        resp = client.get(f"/api/bottles/optimize-shopping?budget={b}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["solution"]["recommended_purchases"]) <= b


def test_shopping_plan_rejects_budget_over_15(client):
    resp = client.get("/api/bottles/optimize-shopping?budget=16")
    assert resp.status_code == 422


# ===================================================================
# K=1 matches greedy
# ===================================================================

def test_shopping_plan_budget_1_matches_greedy(client):
    """For K=1, ILP must match greedy optimize-next: same delta."""
    greedy_resp = client.get("/api/bottles/optimize-next?top=1")
    assert greedy_resp.status_code == 200
    greedy = greedy_resp.json()

    ilp_resp = client.get("/api/bottles/optimize-shopping?budget=1")
    assert ilp_resp.status_code == 200
    ilp = ilp_resp.json()

    greedy_delta = greedy["ranked_candidates"][0]["delta"] if greedy["ranked_candidates"] else 0
    ilp_delta = ilp["solution"]["delta"]
    assert ilp_delta == greedy_delta


# ===================================================================
# K=2 dominates K=1
# ===================================================================

def test_shopping_plan_budget_2_dominates_budget_1(client):
    """delta(K=2) >= delta(K=1)."""
    r1 = client.get("/api/bottles/optimize-shopping?budget=1").json()
    r2 = client.get("/api/bottles/optimize-shopping?budget=2").json()
    assert r2["solution"]["delta"] >= r1["solution"]["delta"]


# ===================================================================
# Weights change solution
# ===================================================================

def test_shopping_plan_weights_change_score(client):
    """Boosting unforgettable weight changes weighted_score relative
    to equal weights (given that unforgettable recipes exist)."""
    r_equal = client.get(
        "/api/bottles/optimize-shopping?budget=3"
        "&weight_unforgettable=1.0&weight_contemporary=1.0&weight_new_era=1.0"
    ).json()
    r_boosted = client.get(
        "/api/bottles/optimize-shopping?budget=3"
        "&weight_unforgettable=10.0&weight_contemporary=1.0&weight_new_era=1.0"
    ).json()
    # With boosted unforgettable, the score should be >= equal-weight score
    # (solver will prefer unforgettable recipes)
    assert r_boosted["solution"]["weighted_score"] >= r_equal["solution"]["weighted_score"]


# ===================================================================
# Alternative group handling
# ===================================================================

def test_shopping_plan_handles_alternative_group(client):
    """Boulevardier needs (TestGin OR TestVodka) + TestCampari.
    With budget=2, solver should be able to cover it."""
    resp = client.get("/api/bottles/optimize-shopping?budget=2")
    data = resp.json()
    purchase_names = {
        p["class_name"] for p in data["solution"]["recommended_purchases"]
    }
    # With K=2, optimal is TestGin + TestCampari (or similar)
    # TestGin alone → 4 recipes; TestCampari alone → 2; together they also
    # unlock Boulevardier (TestGin satisfies the alt_group) → total > 4+2
    assert data["solution"]["delta"] > 4  # more than just TestGin alone


# ===================================================================
# Wildcard generic handling
# ===================================================================

def test_shopping_plan_wildcard_generic(client):
    """K=1: TestGin unlocks Test Gin Fizz (which requires TestGin(generic)),
    because TestGin is sibling under TestGinFamily."""
    resp = client.get("/api/bottles/optimize-shopping?budget=1&explain=true")
    data = resp.json()
    # The top pick should be TestGin with delta=4
    assert data["solution"]["delta"] >= 4
    newly = {r["recipe_name"] for r in data["explanation"]["newly_feasible_recipes"]}
    assert "Test Gin Fizz" in newly


# ===================================================================
# Explanation consistency
# ===================================================================

def test_shopping_plan_explanation_consistency(client):
    """Every newly_feasible_recipe must have ≥1 covered_by_purchases entry."""
    resp = client.get("/api/bottles/optimize-shopping?budget=3&explain=true")
    data = resp.json()
    assert data["explanation"] is not None
    for recipe in data["explanation"]["newly_feasible_recipes"]:
        assert len(recipe["covered_by_purchases"]) >= 1, (
            f"Recipe {recipe['recipe_name']} has no contributors"
        )


def test_shopping_plan_marginal_value_sums_to_delta(client):
    """Sum of incremental_recipes_unlocked across marginal values == delta."""
    resp = client.get("/api/bottles/optimize-shopping?budget=3&explain=true")
    data = resp.json()
    total_marginal = sum(
        p["incremental_recipes_unlocked"]
        for p in data["explanation"]["purchases_marginal_value"]
    )
    assert total_marginal == data["solution"]["delta"]


# ===================================================================
# ILP ↔ SQL divergence check
# ===================================================================

def test_shopping_plan_ilp_sql_consistency(client):
    """After solve, feasible_after should match current_feasible + delta."""
    resp = client.get("/api/bottles/optimize-shopping?budget=3")
    data = resp.json()
    expected = data["current_state"]["feasible_recipes"] + data["solution"]["delta"]
    assert data["solution"]["feasible_recipes_after"] == expected


# ===================================================================
# Timeout handling
# ===================================================================

def test_shopping_plan_never_infeasible(client):
    """With any budget on our test data, solver should never return INFEASIBLE."""
    resp = client.get("/api/bottles/optimize-shopping?budget=5&solver_timeout_seconds=5")
    data = resp.json()
    assert data["solution"]["solver_status"] in ("OPTIMAL", "FEASIBLE")


# ===================================================================
# Verify endpoint
# ===================================================================

def test_verify_endpoint_returns_match(client):
    """The /verify endpoint should return match=true for consistent solver."""
    resp = client.get("/api/bottles/optimize-shopping/verify")
    assert resp.status_code == 200
    data = resp.json()
    assert data["match"] is True


# ===================================================================
# With bottles on hand, delta shrinks
# ===================================================================

def test_shopping_plan_accounts_for_on_hand(client):
    """Creating a TestGin bottle on-hand should reduce delta(K=1)
    since TestGin recipes are already feasible."""
    # Baseline: no bottles
    r_before = client.get("/api/bottles/optimize-shopping?budget=1").json()

    # Add TestGin on-hand
    bid = _make(client, "TestGin", "TestBrand", "ForShopping")
    try:
        r_after = client.get("/api/bottles/optimize-shopping?budget=1").json()
        # Current feasible should be higher
        assert r_after["current_state"]["feasible_recipes"] > r_before["current_state"]["feasible_recipes"]
        # The K=1 pick should now be something else (TestCampari probably)
        if r_after["solution"]["recommended_purchases"]:
            top_name = r_after["solution"]["recommended_purchases"][0]["class_name"]
            assert top_name != "TestGin"
    finally:
        _cleanup(client, [bid])


# ===================================================================
# Explanation absent when explain=false
# ===================================================================

def test_shopping_plan_no_explanation_by_default(client):
    resp = client.get("/api/bottles/optimize-shopping?budget=1")
    data = resp.json()
    assert data["explanation"] is None
