"""Tests for the Shopping Planner page."""

from unittest.mock import patch

_PATCH = "app.routers.shopping.fetch_optimize_shopping"

# --- Mock data ---

_SHOPPING_RESULT = {
    "budget": 3,
    "weights": {"unforgettable": 1.0, "contemporary": 1.0, "new_era": 1.0},
    "current_state": {"feasible_recipes": 18, "on_hand_class_ids_count": 24},
    "solution": {
        "recommended_purchases": [
            {"class_id": 32, "class_name": "White Rum", "parent_family": "Rum", "equivalent_alternatives": []},
            {"class_id": 50, "class_name": "Cognac", "parent_family": "Brandy", "equivalent_alternatives": ["Armagnac"]},
            {"class_id": 60, "class_name": "Triple Sec", "parent_family": "Liqueur", "equivalent_alternatives": ["Cointreau", "Grand Marnier", "Curaçao", "Combier"]},
        ],
        "feasible_recipes_after": 25,
        "delta": 7,
        "weighted_score": 7.0,
        "is_optimal": True,
        "solver_status": "OPTIMAL",
        "computation_time_ms": 120,
    },
    "explanation": {
        "newly_feasible_recipes": [
            {"recipe_id": 7, "recipe_name": "Between The Sheets", "iba_category": "unforgettable", "covered_by_purchases": ["White Rum", "Cognac", "Triple Sec"]},
            {"recipe_id": 10, "recipe_name": "Cosmopolitan", "iba_category": "contemporary", "covered_by_purchases": ["Triple Sec"]},
            {"recipe_id": 20, "recipe_name": "Daiquiri", "iba_category": "unforgettable", "covered_by_purchases": ["White Rum"]},
            {"recipe_id": 30, "recipe_name": "Mojito", "iba_category": "contemporary", "covered_by_purchases": ["White Rum"]},
            {"recipe_id": 40, "recipe_name": "Sidecar", "iba_category": "unforgettable", "covered_by_purchases": ["Cognac", "Triple Sec"]},
            {"recipe_id": 50, "recipe_name": "Spicy Fifty", "iba_category": "new_era", "covered_by_purchases": ["Triple Sec"]},
            {"recipe_id": 60, "recipe_name": "Mai Tai", "iba_category": "contemporary", "covered_by_purchases": ["White Rum", "Triple Sec"]},
        ],
        "purchases_marginal_value": [
            {"class_name": "White Rum", "incremental_recipes_unlocked": 2, "incremental_weighted_value": 2.0},
            {"class_name": "Cognac", "incremental_recipes_unlocked": 3, "incremental_weighted_value": 3.0},
            {"class_name": "Triple Sec", "incremental_recipes_unlocked": 2, "incremental_weighted_value": 2.0},
        ],
    },
}

_SHOPPING_TIMEOUT = {
    **_SHOPPING_RESULT,
    "solution": {
        **_SHOPPING_RESULT["solution"],
        "is_optimal": False,
        "solver_status": "FEASIBLE",
    },
}

_SHOPPING_ZERO_DELTA = {
    **_SHOPPING_RESULT,
    "solution": {
        **_SHOPPING_RESULT["solution"],
        "recommended_purchases": [],
        "feasible_recipes_after": 18,
        "delta": 0,
    },
    "explanation": {
        "newly_feasible_recipes": [],
        "purchases_marginal_value": [],
    },
}


def test_shopping_returns_200_and_default_results(client):
    with patch(_PATCH, return_value=_SHOPPING_RESULT):
        resp = client.get("/shopping")
    assert resp.status_code == 200
    assert "Shopping Planner" in resp.text
    assert "+7" in resp.text


def test_shopping_results_partial_for_htmx(client):
    with patch(_PATCH, return_value=_SHOPPING_RESULT):
        resp = client.get("/shopping/results", headers={"HX-Request": "true"})
    assert resp.status_code == 200
    assert "<html" not in resp.text
    assert "+7" in resp.text


def test_shopping_budget_change_triggers_recompute(client):
    with patch(_PATCH, return_value=_SHOPPING_RESULT) as mock:
        client.get("/shopping/results?budget=5&wu=2&wc=2&wn=2",
                    headers={"HX-Request": "true"})
    mock.assert_called_once_with(
        budget=5,
        weight_unforgettable=1.0,
        weight_contemporary=1.0,
        weight_new_era=1.0,
    )


def test_shopping_weight_mapping_correct(client):
    with patch(_PATCH, return_value=_SHOPPING_RESULT) as mock:
        client.get("/shopping/results?budget=3&wu=0&wc=2&wn=4",
                    headers={"HX-Request": "true"})
    mock.assert_called_once_with(
        budget=3,
        weight_unforgettable=0.0,
        weight_contemporary=1.0,
        weight_new_era=2.0,
    )


def test_shopping_displays_delta_prominently(client):
    with patch(_PATCH, return_value=_SHOPPING_RESULT):
        resp = client.get("/shopping")
    html = resp.text
    assert "+7" in html
    assert "additional cocktails unlocked" in html


def test_shopping_lists_recommended_purchases(client):
    with patch(_PATCH, return_value=_SHOPPING_RESULT):
        resp = client.get("/shopping")
    html = resp.text
    assert "White Rum" in html
    assert "Cognac" in html
    assert "Triple Sec" in html


def test_shopping_groups_newly_feasible_by_category(client):
    with patch(_PATCH, return_value=_SHOPPING_RESULT):
        resp = client.get("/shopping")
    html = resp.text
    assert "Unforgettable" in html
    assert "Contemporary" in html
    assert "New Era" in html


def test_shopping_purchases_link_to_cocktail_detail(client):
    with patch(_PATCH, return_value=_SHOPPING_RESULT):
        resp = client.get("/shopping")
    html = resp.text
    assert 'hx-get="/cocktail/7"' in html
    assert 'hx-get="/cocktail/20"' in html
    assert 'hx-get="/cocktail/50"' in html


def test_shopping_handles_optimal_status(client):
    with patch(_PATCH, return_value=_SHOPPING_RESULT):
        resp = client.get("/shopping")
    assert "OPTIMAL" in resp.text


def test_shopping_handles_feasible_timeout_status(client):
    with patch(_PATCH, return_value=_SHOPPING_TIMEOUT):
        resp = client.get("/shopping")
    assert "FEASIBLE (timeout)" in resp.text


def test_shopping_handles_zero_delta(client):
    with patch(_PATCH, return_value=_SHOPPING_ZERO_DELTA):
        resp = client.get("/shopping")
    assert "No new cocktails unlocked" in resp.text


def test_shopping_handles_backend_error(client):
    import httpx
    with patch(_PATCH, side_effect=httpx.ConnectError("connection refused")):
        resp = client.get("/shopping")
    assert resp.status_code == 200
    assert "Error computing picks" in resp.text


def test_shopping_equivalent_alternatives_displayed(client):
    with patch(_PATCH, return_value=_SHOPPING_RESULT):
        resp = client.get("/shopping")
    html = resp.text
    assert "Equivalent alternatives" in html
    assert "Cointreau" in html
    # Triple Sec has 4 alternatives, should show "+1 more"
    assert "+1 more" in html
