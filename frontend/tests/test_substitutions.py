"""Tests for the Substitutions / Evaluate alternatives page."""

from unittest.mock import patch

import httpx

_PATCH_SUBS = "app.routers.substitutions.fetch_recipe_substitutions"
_PATCH_DETAIL_RECIPE = "app.routers.substitutions.fetch_recipe_detail"
_PATCH_DETAIL = "app.routers.detail.fetch_recipe_detail"
_PATCH_FEAS = "app.routers.detail.fetch_cocktail_feasibility"

# --- Mock data ---

_SUBS_RESULT = {
    "recipe": {"id": 50, "name": "Manhattan", "iba_category": "unforgettable"},
    "current_feasibility": {"can_make": False, "missing_count": 1},
    "ingredients_analysis": [
        {
            "recipe_ingredient_id": 234,
            "class_name": "Rye Whiskey",
            "parent_family": "Whiskey",
            "amount": 60,
            "unit": "ml",
            "is_satisfied": False,
            "anti_doppione_classes": ["Vermouth Rosso", "Angostura Aromatic Bitters"],
            "substitutions": {
                "strict": [
                    {
                        "bottle": {"id": 20, "brand": "Buffalo Trace", "label": "Kentucky Straight Bourbon", "class_name": "Bourbon (generic)"},
                        "distance": 0.23,
                        "tier": "strict",
                        "rationale": "Same family (Whiskey), close profile",
                    },
                ],
                "loose": [
                    {
                        "bottle": {"id": 30, "brand": "Laphroaig", "label": "10 Year Old", "class_name": "Scotch Whisky"},
                        "distance": 0.45,
                        "tier": "loose",
                        "rationale": "Different family, moderate similarity",
                    },
                ],
            },
        },
    ],
}

_SUBS_TWO_MISSING = {
    "recipe": {"id": 50, "name": "Manhattan", "iba_category": "unforgettable"},
    "current_feasibility": {"can_make": False, "missing_count": 2},
    "ingredients_analysis": [
        {
            "recipe_ingredient_id": 234,
            "class_name": "Rye Whiskey",
            "parent_family": "Whiskey",
            "amount": 60,
            "unit": "ml",
            "is_satisfied": False,
            "anti_doppione_classes": [],
            "substitutions": {
                "strict": [
                    {"bottle": {"id": 20, "brand": "Buffalo Trace", "label": "Bourbon", "class_name": "Bourbon"}, "distance": 0.23, "tier": "strict", "rationale": "Same family"},
                ],
                "loose": [],
            },
        },
        {
            "recipe_ingredient_id": 235,
            "class_name": "Angostura Bitters",
            "parent_family": "Bitters",
            "amount": 2,
            "unit": "dash",
            "is_satisfied": False,
            "anti_doppione_classes": [],
            "substitutions": {
                "strict": [
                    {"bottle": {"id": 40, "brand": "Peychaud's", "label": "Bitters", "class_name": "Peychaud's Bitters"}, "distance": 0.31, "tier": "strict", "rationale": "Same family"},
                ],
                "loose": [],
            },
        },
    ],
}

_SUBS_STRICT_ONLY = {
    "recipe": {"id": 50, "name": "Manhattan", "iba_category": "unforgettable"},
    "current_feasibility": {"can_make": False, "missing_count": 1},
    "ingredients_analysis": [
        {
            "recipe_ingredient_id": 234,
            "class_name": "Rye Whiskey",
            "parent_family": "Whiskey",
            "amount": 60,
            "unit": "ml",
            "is_satisfied": False,
            "anti_doppione_classes": [],
            "substitutions": {
                "strict": [
                    {"bottle": {"id": 20, "brand": "Buffalo Trace", "label": "Bourbon", "class_name": "Bourbon"}, "distance": 0.23, "tier": "strict", "rationale": "Same family"},
                ],
                "loose": [],
            },
        },
    ],
}

_SUBS_FEASIBLE = {
    "recipe": {"id": 50, "name": "Manhattan", "iba_category": "unforgettable"},
    "current_feasibility": {"can_make": True, "missing_count": 0},
    "ingredients_analysis": [
        {
            "recipe_ingredient_id": 234,
            "class_name": "Rye Whiskey",
            "parent_family": "Whiskey",
            "amount": 60,
            "unit": "ml",
            "is_satisfied": True,
            "satisfied_by_bottles": [{"id": 10, "brand": "Rittenhouse", "label": "Rye 100"}],
            "anti_doppione_classes": ["Vermouth Rosso"],
            "substitutions": {
                "strict": [
                    {"bottle": {"id": 20, "brand": "Buffalo Trace", "label": "Bourbon", "class_name": "Bourbon"}, "distance": 0.23, "tier": "strict", "rationale": "Same family"},
                ],
                "loose": [],
            },
        },
    ],
}

_SUBS_FEASIBLE_NO_ALTS = {
    "recipe": {"id": 50, "name": "Manhattan", "iba_category": "unforgettable"},
    "current_feasibility": {"can_make": True, "missing_count": 0},
    "ingredients_analysis": [
        {
            "recipe_ingredient_id": 234,
            "class_name": "Rye Whiskey",
            "parent_family": "Whiskey",
            "amount": 60,
            "unit": "ml",
            "is_satisfied": True,
            "satisfied_by_bottles": [{"id": 10, "brand": "Rittenhouse", "label": "Rye 100"}],
            "anti_doppione_classes": [],
            "substitutions": {"strict": [], "loose": []},
        },
    ],
}

_SUBS_NO_SUBSTITUTES = {
    "recipe": {"id": 50, "name": "Manhattan", "iba_category": "unforgettable"},
    "current_feasibility": {"can_make": False, "missing_count": 1},
    "ingredients_analysis": [
        {
            "recipe_ingredient_id": 234,
            "class_name": "Rye Whiskey",
            "parent_family": "Whiskey",
            "amount": 60,
            "unit": "ml",
            "is_satisfied": False,
            "anti_doppione_classes": [],
            "substitutions": {"strict": [], "loose": []},
        },
    ],
}

_SUBS_WITH_NOTE = {
    "recipe": {"id": 50, "name": "Manhattan", "iba_category": "unforgettable"},
    "current_feasibility": {"can_make": False, "missing_count": 1},
    "ingredients_analysis": [
        {
            "recipe_ingredient_id": 234,
            "class_name": "Rye Whiskey",
            "parent_family": "Whiskey",
            "amount": 60,
            "unit": "ml",
            "is_satisfied": False,
            "anti_doppione_classes": [],
            "note": "Alternative group, suggestions apply to any of [Rye Whiskey, Bourbon]",
            "substitutions": {
                "strict": [
                    {"bottle": {"id": 20, "brand": "Buffalo Trace", "label": "Bourbon", "class_name": "Bourbon"}, "distance": 0.23, "tier": "strict", "rationale": "Same family"},
                ],
                "loose": [],
            },
        },
    ],
}

# Detail page mock data
_RECIPE = {
    "id": 42,
    "name": "Negroni",
    "iba_category": "unforgettable",
    "method": "Stir all ingredients.",
    "glass": "old fashioned",
    "garnish": "Orange slice",
    "source_url": None,
    "ingredients": [
        {"class_id": 1, "class_name": "Gin", "amount": 30.0, "unit": "ml",
         "is_optional": False, "is_garnish": False, "alternative_group_id": None, "raw_name": "Gin"},
    ],
}

_FEAS_CAN_MAKE = {
    "recipe": {"id": 42, "name": "Negroni", "iba_category": "unforgettable", "glass": "old fashioned", "ingredient_count": 1},
    "can_make": True,
    "ingredients": [
        {"class_name": "Gin", "satisfied_by_bottles": [{"id": 10, "brand": "Tanqueray", "label": None}],
         "is_optional": False, "is_garnish": False, "is_commodity": False, "alternative_group_id": None},
    ],
}

_FEAS_CANNOT_MAKE = {
    **_FEAS_CAN_MAKE,
    "can_make": False,
    "ingredients": [
        {"class_name": "Gin", "satisfied_by_bottles": [],
         "is_optional": False, "is_garnish": False, "is_commodity": False, "alternative_group_id": None},
    ],
}


# --- Substitutions page tests ---

def test_substitutions_returns_200_for_valid_recipe(client):
    with patch(_PATCH_SUBS, return_value=_SUBS_RESULT):
        resp = client.get("/cocktail/50/substitutions")
    assert resp.status_code == 200
    assert "Evaluate alternatives for Manhattan" in resp.text


def test_substitutions_returns_404_for_invalid_recipe(client):
    exc = httpx.HTTPStatusError(
        "Not Found",
        request=httpx.Request("GET", "http://test/api/recipes/999/substitutions"),
        response=httpx.Response(404),
    )
    with patch(_PATCH_SUBS, side_effect=exc):
        resp = client.get("/cocktail/999/substitutions")
    assert resp.status_code == 404


def test_substitutions_shows_satisfied_ingredients(client):
    with patch(_PATCH_SUBS, return_value=_SUBS_FEASIBLE):
        resp = client.get("/cocktail/50/substitutions")
    assert resp.status_code == 200
    assert "Evaluate alternatives" in resp.text
    assert "On hand" in resp.text
    assert "Rye Whiskey" in resp.text
    assert "Buffalo Trace" in resp.text


def test_substitutions_satisfied_no_alternatives(client):
    """Satisfied ingredients with no alternative bottles show per-ingredient message."""
    with patch(_PATCH_SUBS, return_value=_SUBS_FEASIBLE_NO_ALTS):
        resp = client.get("/cocktail/50/substitutions")
    assert resp.status_code == 200
    assert "On hand" in resp.text
    assert "No substitutes found" in resp.text


def test_substitutions_shows_ingredients_grouped(client):
    with patch(_PATCH_SUBS, return_value=_SUBS_TWO_MISSING):
        resp = client.get("/cocktail/50/substitutions")
    html = resp.text
    assert "Rye Whiskey" in html
    assert "Angostura Bitters" in html


def test_substitutions_lists_strict_and_loose_when_tier_both(client):
    with patch(_PATCH_SUBS, return_value=_SUBS_RESULT):
        resp = client.get("/cocktail/50/substitutions?tier=both")
    html = resp.text
    assert "STRICT" in html.upper()
    assert "LOOSE" in html.upper()


def test_substitutions_filters_strict_only(client):
    with patch(_PATCH_SUBS, return_value=_SUBS_STRICT_ONLY):
        resp = client.get("/cocktail/50/substitutions?tier=strict")
    html = resp.text
    assert "Strict" in html
    assert "Laphroaig" not in html


def test_substitutions_displays_distance_values(client):
    with patch(_PATCH_SUBS, return_value=_SUBS_RESULT):
        resp = client.get("/cocktail/50/substitutions")
    assert "0.23" in resp.text
    assert "0.45" in resp.text


def test_substitutions_displays_rationale(client):
    with patch(_PATCH_SUBS, return_value=_SUBS_RESULT):
        resp = client.get("/cocktail/50/substitutions")
    assert "Same family (Whiskey), close profile" in resp.text


def test_substitutions_displays_anti_doppione_classes(client):
    with patch(_PATCH_SUBS, return_value=_SUBS_RESULT):
        resp = client.get("/cocktail/50/substitutions")
    assert "Excluded from suggestions (already in recipe)" in resp.text
    assert "Vermouth Rosso" in resp.text
    assert "Angostura Aromatic Bitters" in resp.text


def test_substitutions_empty_state_no_substitutes(client):
    with patch(_PATCH_SUBS, return_value=_SUBS_NO_SUBSTITUTES):
        resp = client.get("/cocktail/50/substitutions")
    # Ingredient shown with per-ingredient "no subs" message
    assert "Rye Whiskey" in resp.text
    assert "No substitutes found" in resp.text


def test_substitutions_empty_state_no_ingredients(client):
    """Global empty state only when ingredients_analysis is empty."""
    empty = {
        "recipe": {"id": 50, "name": "Manhattan", "iba_category": "unforgettable"},
        "current_feasibility": {"can_make": True, "missing_count": 0},
        "ingredients_analysis": [],
    }
    with patch(_PATCH_SUBS, return_value=empty):
        resp = client.get("/cocktail/50/substitutions")
    assert "No reference profile available" in resp.text
    assert "Shopping Planner" in resp.text


def test_substitutions_per_ingredient_no_subs_message(client):
    """When one ingredient has subs and another doesn't, show per-ingredient message."""
    mixed = {
        **_SUBS_TWO_MISSING,
        "ingredients_analysis": [
            _SUBS_TWO_MISSING["ingredients_analysis"][0],  # has subs
            {**_SUBS_TWO_MISSING["ingredients_analysis"][1],
             "substitutions": {"strict": [], "loose": []}},  # no subs
        ],
    }
    with patch(_PATCH_SUBS, return_value=mixed):
        resp = client.get("/cocktail/50/substitutions")
    assert "No substitutes found" in resp.text


def test_substitutions_card_has_radio_input(client):
    with patch(_PATCH_SUBS, return_value=_SUBS_RESULT):
        resp = client.get("/cocktail/50/substitutions")
    assert 'name="swap_0"' in resp.text
    assert 'type="radio"' in resp.text


def test_substitutions_handles_alternative_group_note(client):
    with patch(_PATCH_SUBS, return_value=_SUBS_WITH_NOTE):
        resp = client.get("/cocktail/50/substitutions")
    assert "Alternative group, suggestions apply to any of" in resp.text


def test_substitutions_partial_response_for_htmx_tier_filter(client):
    """HTMX request targeting substitutions-content returns partial."""
    with patch(_PATCH_SUBS, return_value=_SUBS_RESULT):
        resp = client.get("/cocktail/50/substitutions?tier=both",
                          headers={"HX-Request": "true", "HX-Target": "substitutions-content"})
    assert resp.status_code == 200
    assert "<html" not in resp.text
    assert "Rye Whiskey" in resp.text


def test_substitutions_full_page_for_htmx_main_content(client):
    """HTMX request targeting main-content returns full page block."""
    with patch(_PATCH_SUBS, return_value=_SUBS_RESULT):
        resp = client.get("/cocktail/50/substitutions",
                          headers={"HX-Request": "true", "HX-Target": "main-content"})
    assert resp.status_code == 200
    assert "Evaluate alternatives for Manhattan" in resp.text
    assert "Preview with swaps" in resp.text


def test_detail_page_shows_evaluate_alternatives_link(client):
    with patch(_PATCH_DETAIL, return_value=_RECIPE), \
         patch(_PATCH_FEAS, return_value=_FEAS_CANNOT_MAKE):
        resp = client.get("/cocktail/42")
    assert 'Evaluate alternatives' in resp.text
    assert '/cocktail/42/substitutions' in resp.text


def test_detail_page_shows_evaluate_alternatives_for_makeable(client):
    with patch(_PATCH_DETAIL, return_value=_RECIPE), \
         patch(_PATCH_FEAS, return_value=_FEAS_CAN_MAKE):
        resp = client.get("/cocktail/42")
    assert 'Evaluate alternatives' in resp.text
    assert '/cocktail/42/substitutions' in resp.text


_RECIPE_MANHATTAN = {
    "id": 50,
    "name": "Manhattan",
    "method": "Stir",
    "garnish": "Cherry",
    "ingredients": [
        {"class_name": "Rye Whiskey", "amount": 60.0, "unit": "ml",
         "is_optional": False, "is_garnish": False, "is_commodity": False},
        {"class_name": "Vermouth Rosso", "amount": 30.0, "unit": "ml",
         "is_optional": False, "is_garnish": False, "is_commodity": False},
        {"class_name": "Angostura Aromatic Bitters", "amount": 2.0, "unit": "dash",
         "is_optional": False, "is_garnish": False, "is_commodity": True},
    ],
}


def test_preview_renders_with_swaps(client):
    with patch(_PATCH_SUBS, return_value=_SUBS_RESULT), \
         patch(_PATCH_DETAIL_RECIPE, return_value=_RECIPE_MANHATTAN):
        resp = client.post(
            "/cocktail/50/substitutions/preview",
            data={"swap_0": "20:Buffalo Trace:Kentucky Straight Bourbon:Bourbon (generic)"},
        )
    assert resp.status_code == 200
    assert "Preview: Manhattan" in resp.text
    assert "Buffalo Trace" in resp.text
    assert "swapped" in resp.text
    assert "1 swap" in resp.text


def test_preview_shows_commodities(client):
    """Preview should include commodity ingredients."""
    with patch(_PATCH_SUBS, return_value=_SUBS_RESULT), \
         patch(_PATCH_DETAIL_RECIPE, return_value=_RECIPE_MANHATTAN):
        resp = client.post(
            "/cocktail/50/substitutions/preview",
            data={},
        )
    assert resp.status_code == 200
    assert "Angostura Aromatic Bitters" in resp.text
    assert "commodity" in resp.text


def test_preview_no_swaps(client):
    with patch(_PATCH_SUBS, return_value=_SUBS_RESULT), \
         patch(_PATCH_DETAIL_RECIPE, return_value={**_RECIPE_MANHATTAN, "garnish": None}):
        resp = client.post(
            "/cocktail/50/substitutions/preview",
            data={},
        )
    assert resp.status_code == 200
    assert "0 swaps" in resp.text
