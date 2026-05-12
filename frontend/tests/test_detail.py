"""Tests for the cocktail detail page."""

from unittest.mock import patch

import httpx

# --- Mock data ---

_RECIPE = {
    "id": 42,
    "name": "Negroni",
    "iba_category": "unforgettable",
    "method": "Stir all ingredients with ice and strain into a chilled glass.",
    "glass": "old fashioned",
    "garnish": "Garnish with half orange slice.",
    "source_url": "https://iba-world.com/iba-cocktail/negroni/",
    "ingredients": [
        {"class_id": 1, "class_name": "London Dry Gin", "amount": 30.0, "unit": "ml",
         "is_optional": False, "is_garnish": False, "alternative_group_id": None, "raw_name": "Gin"},
        {"class_id": 2, "class_name": "Campari", "amount": 30.0, "unit": "ml",
         "is_optional": False, "is_garnish": False, "alternative_group_id": None, "raw_name": "Campari"},
        {"class_id": 3, "class_name": "Sweet Vermouth", "amount": 30.0, "unit": "ml",
         "is_optional": False, "is_garnish": False, "alternative_group_id": None, "raw_name": "Sweet Red Vermouth"},
    ],
}

_FEASIBILITY_CAN_MAKE = {
    "recipe": {"id": 42, "name": "Negroni", "iba_category": "unforgettable", "glass": "old fashioned", "ingredient_count": 3},
    "can_make": True,
    "ingredients": [
        {"class_name": "London Dry Gin", "satisfied_by_bottles": [{"id": 10, "brand": "Tanqueray", "label": "No. Ten"}],
         "is_optional": False, "is_garnish": False, "is_commodity": False, "alternative_group_id": None},
        {"class_name": "Campari", "satisfied_by_bottles": [{"id": 11, "brand": "Campari", "label": "Bitter"}],
         "is_optional": False, "is_garnish": False, "is_commodity": False, "alternative_group_id": None},
        {"class_name": "Sweet Vermouth", "satisfied_by_bottles": [{"id": 12, "brand": "Carpano", "label": "Antica Formula"}],
         "is_optional": False, "is_garnish": False, "is_commodity": False, "alternative_group_id": None},
    ],
}

_FEASIBILITY_CANNOT_MAKE = {
    "recipe": {"id": 42, "name": "Negroni", "iba_category": "unforgettable", "glass": "old fashioned", "ingredient_count": 3},
    "can_make": False,
    "ingredients": [
        {"class_name": "London Dry Gin", "satisfied_by_bottles": [{"id": 10, "brand": "Tanqueray", "label": "No. Ten"}],
         "is_optional": False, "is_garnish": False, "is_commodity": False, "alternative_group_id": None},
        {"class_name": "Campari", "satisfied_by_bottles": [],
         "is_optional": False, "is_garnish": False, "is_commodity": False, "alternative_group_id": None},
        {"class_name": "Sweet Vermouth", "satisfied_by_bottles": [],
         "is_optional": False, "is_garnish": False, "is_commodity": False, "alternative_group_id": None},
    ],
}

_RECIPE_COMMODITY = {
    "id": 99,
    "name": "Juice Mix",
    "iba_category": "new_era",
    "method": "Mix everything.",
    "glass": "highball",
    "garnish": None,
    "source_url": None,
    "ingredients": [
        {"class_id": 5, "class_name": "Soda Water", "amount": 90.0, "unit": "ml",
         "is_optional": False, "is_garnish": False, "alternative_group_id": None, "raw_name": "Soda Water"},
    ],
}

_FEASIBILITY_COMMODITY = {
    "recipe": {"id": 99, "name": "Juice Mix", "iba_category": "new_era", "glass": "highball", "ingredient_count": 1},
    "can_make": True,
    "ingredients": [
        {"class_name": "Soda Water", "satisfied_by_bottles": [],
         "is_optional": False, "is_garnish": False, "is_commodity": True, "alternative_group_id": None},
    ],
}

_RECIPE_ALT_GROUP = {
    "id": 77,
    "name": "Boulevardier",
    "iba_category": "unforgettable",
    "method": "Stir with ice, strain.",
    "glass": "old fashioned",
    "garnish": "Orange zest.",
    "source_url": None,
    "ingredients": [
        {"class_id": 10, "class_name": "Bourbon", "amount": 45.0, "unit": "ml",
         "is_optional": False, "is_garnish": False, "alternative_group_id": 1, "raw_name": "Bourbon"},
        {"class_id": 11, "class_name": "Rye Whiskey", "amount": 45.0, "unit": "ml",
         "is_optional": False, "is_garnish": False, "alternative_group_id": 1, "raw_name": "Rye"},
        {"class_id": 2, "class_name": "Campari", "amount": 30.0, "unit": "ml",
         "is_optional": False, "is_garnish": False, "alternative_group_id": None, "raw_name": "Campari"},
    ],
}

_FEASIBILITY_ALT_GROUP = {
    "recipe": {"id": 77, "name": "Boulevardier", "iba_category": "unforgettable", "glass": "old fashioned", "ingredient_count": 3},
    "can_make": False,
    "ingredients": [
        {"class_name": "Bourbon", "satisfied_by_bottles": [],
         "is_optional": False, "is_garnish": False, "is_commodity": False, "alternative_group_id": 1},
        {"class_name": "Rye Whiskey", "satisfied_by_bottles": [],
         "is_optional": False, "is_garnish": False, "is_commodity": False, "alternative_group_id": 1},
        {"class_name": "Campari", "satisfied_by_bottles": [],
         "is_optional": False, "is_garnish": False, "is_commodity": False, "alternative_group_id": None},
    ],
}

# Reuse can-make-now sample from test_home
_HOME_ITEMS = {
    "summary": {"total_recipes": 77, "can_make": 1, "cannot_make": 76, "on_hand_classes": 5},
    "items": [
        {"id": 42, "name": "Negroni", "iba_category": "unforgettable", "glass": "old fashioned",
         "can_make": True, "missing_count": 0, "missing_classes": []},
    ],
}


def _mock_detail(recipe, feasibility):
    return (
        patch("app.routers.detail.fetch_recipe_detail", return_value=recipe),
        patch("app.routers.detail.fetch_cocktail_feasibility", return_value=feasibility),
    )


def _mock_404():
    exc = httpx.HTTPStatusError(
        "Not Found",
        request=httpx.Request("GET", "http://fake/api/recipes/999"),
        response=httpx.Response(404),
    )
    return (
        patch("app.routers.detail.fetch_recipe_detail", side_effect=exc),
        patch("app.routers.detail.fetch_cocktail_feasibility", side_effect=exc),
    )


# --- Tests ---

def test_cocktail_detail_returns_200_for_valid_id(client):
    m1, m2 = _mock_detail(_RECIPE, _FEASIBILITY_CAN_MAKE)
    with m1, m2:
        resp = client.get("/cocktail/42")
    assert resp.status_code == 200
    assert "Negroni" in resp.text


def test_cocktail_detail_returns_404_for_invalid_id(client):
    m1, m2 = _mock_404()
    with m1, m2:
        resp = client.get("/cocktail/999")
    assert resp.status_code == 404
    assert "Cocktail not found" in resp.text
    assert "Back to home" in resp.text


def test_cocktail_detail_shows_feasible_badge(client):
    m1, m2 = _mock_detail(_RECIPE, _FEASIBILITY_CAN_MAKE)
    with m1, m2:
        resp = client.get("/cocktail/42")
    assert "Can make now" in resp.text


def test_cocktail_detail_shows_not_feasible_badge(client):
    m1, m2 = _mock_detail(_RECIPE, _FEASIBILITY_CANNOT_MAKE)
    with m1, m2:
        resp = client.get("/cocktail/42")
    assert "Cannot make" in resp.text
    assert "Coming soon" in resp.text


def test_cocktail_detail_renders_ingredients_with_amounts(client):
    m1, m2 = _mock_detail(_RECIPE, _FEASIBILITY_CAN_MAKE)
    with m1, m2:
        resp = client.get("/cocktail/42")
    assert "30 ml" in resp.text
    assert "London Dry Gin" in resp.text


def test_cocktail_detail_shows_satisfying_bottle(client):
    m1, m2 = _mock_detail(_RECIPE, _FEASIBILITY_CAN_MAKE)
    with m1, m2:
        resp = client.get("/cocktail/42")
    assert "Tanqueray" in resp.text
    assert "No. Ten" in resp.text


def test_cocktail_detail_shows_missing_for_unsatisfied_ingredient(client):
    m1, m2 = _mock_detail(_RECIPE, _FEASIBILITY_CANNOT_MAKE)
    with m1, m2:
        resp = client.get("/cocktail/42")
    assert "missing" in resp.text


def test_cocktail_detail_shows_commodity_marker(client):
    m1, m2 = _mock_detail(_RECIPE_COMMODITY, _FEASIBILITY_COMMODITY)
    with m1, m2:
        resp = client.get("/cocktail/99")
    assert "always available" in resp.text


def test_cocktail_detail_groups_alternative_ingredients(client):
    m1, m2 = _mock_detail(_RECIPE_ALT_GROUP, _FEASIBILITY_ALT_GROUP)
    with m1, m2:
        resp = client.get("/cocktail/77")
    assert "Choose one of:" in resp.text
    assert "Bourbon" in resp.text
    assert "Rye Whiskey" in resp.text


def test_cocktail_detail_partial_response_for_htmx_request(client):
    m1, m2 = _mock_detail(_RECIPE, _FEASIBILITY_CAN_MAKE)
    with m1, m2:
        resp = client.get("/cocktail/42", headers={"HX-Request": "true"})
    assert resp.status_code == 200
    assert "<!DOCTYPE html>" not in resp.text
    assert "Negroni" in resp.text


def test_cocktail_detail_full_response_for_direct_request(client):
    m1, m2 = _mock_detail(_RECIPE, _FEASIBILITY_CAN_MAKE)
    with m1, m2:
        resp = client.get("/cocktail/42")
    assert "<!DOCTYPE html>" in resp.text


def test_home_card_links_to_detail(client):
    with patch("app.routers.home.fetch_cocktails_can_make_now", return_value=_HOME_ITEMS):
        resp = client.get("/")
    assert 'hx-get="/cocktail/42"' in resp.text
    assert 'hx-push-url="true"' in resp.text
