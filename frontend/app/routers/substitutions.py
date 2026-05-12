import logging

import httpx
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from app.client import fetch_recipe_detail, fetch_recipe_substitutions
from app.templating import templates

logger = logging.getLogger(__name__)
router = APIRouter()

_VALID_TIERS = {"both", "strict", "loose"}


def _build_ctx(recipe_id: int, tier: str) -> dict:
    if tier not in _VALID_TIERS:
        tier = "both"

    try:
        data = fetch_recipe_substitutions(
            recipe_id, tier=tier, include_satisfied=True,
        )
        error = None
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return {"not_found": True}
        logger.exception("Backend substitutions call failed for %s", recipe_id)
        return {"error": "backend_error", "recipe_name": f"Recipe #{recipe_id}"}
    except httpx.HTTPError:
        logger.exception("Backend substitutions call failed for %s", recipe_id)
        return {"error": "backend_error", "recipe_name": f"Recipe #{recipe_id}"}

    recipe = data.get("recipe", {})
    feas = data.get("current_feasibility", {})
    missing_count = feas.get("missing_count", 0)
    ingredients = data.get("ingredients_analysis", [])

    for ing in ingredients:
        subs = ing.get("substitutions", {})
        strict = subs.get("strict", [])
        loose = subs.get("loose", [])
        combined = sorted(strict + loose, key=lambda s: s.get("distance", 999))
        ing["all_substitutions"] = combined[:10]
        ing["has_any"] = len(combined) > 0

    any_subs = any(ing["has_any"] for ing in ingredients)

    return {
        "error": error,
        "recipe_id": recipe_id,
        "recipe_name": recipe.get("name", ""),
        "iba_category": recipe.get("iba_category", ""),
        "missing_count": missing_count,
        "ingredients": ingredients,
        "any_subs": any_subs,
        "tier": tier,
    }


@router.get("/cocktail/{recipe_id}/substitutions", response_class=HTMLResponse)
def substitutions_page(request: Request, recipe_id: int, tier: str = "both"):
    ctx = _build_ctx(recipe_id, tier)

    if ctx.get("not_found"):
        resp = templates.TemplateResponse(
            request, "_404.html", {"message": "Cocktail not found"},
        )
        resp.status_code = 404
        return resp

    is_htmx = request.headers.get("HX-Request") == "true"
    hx_target = request.headers.get("HX-Target", "")
    if is_htmx and hx_target == "substitutions-content":
        return templates.TemplateResponse(
            request, "_substitutions_content.html", ctx,
        )
    return templates.TemplateResponse(request, "substitutions.html", ctx)


@router.post("/cocktail/{recipe_id}/substitutions/preview", response_class=HTMLResponse)
async def substitutions_preview(request: Request, recipe_id: int):
    """Render ephemeral recipe view with user-selected swaps."""
    form = await request.form()

    # Collect swap selections: swap_<idx> = "bottle_id:brand:label:class_name"
    swaps: dict[int, dict] = {}
    for key, value in form.items():
        if key.startswith("swap_") and value:
            try:
                idx = int(key.split("_", 1)[1])
                parts = str(value).split(":", 3)
                if len(parts) == 4:
                    swaps[idx] = {
                        "bottle_id": int(parts[0]),
                        "brand": parts[1],
                        "label": parts[2],
                        "class_name": parts[3],
                    }
            except (ValueError, IndexError):
                continue

    # Fetch original recipe for metadata
    try:
        recipe = fetch_recipe_detail(recipe_id)
    except httpx.HTTPError:
        logger.exception("Cannot fetch recipe %s for preview", recipe_id)
        recipe = {"id": recipe_id, "name": f"Recipe #{recipe_id}"}

    # Fetch substitutions data to rebuild ingredient list
    ctx_data = _build_ctx(recipe_id, "both")
    if ctx_data.get("not_found") or ctx_data.get("error"):
        return templates.TemplateResponse(
            request, "_404.html", {"message": "Cannot build preview"},
            status_code=502,
        )

    # Build swap lookup from substitution ingredients (keyed by index)
    sub_ingredients = ctx_data["ingredients"]
    sub_by_class = {ing["class_name"]: ing for ing in sub_ingredients}

    # Build preview from the FULL recipe ingredient list
    recipe_ingredients = recipe.get("ingredients", [])
    preview_ingredients = []
    swap_idx = 0
    for ri in recipe_ingredients:
        entry = {
            "class_name": ri["class_name"],
            "amount": ri.get("amount"),
            "unit": ri.get("unit"),
            "is_optional": ri.get("is_optional", False),
            "is_garnish": ri.get("is_garnish", False),
            "is_commodity": ri.get("is_commodity", False),
        }
        sub_ing = sub_by_class.get(ri["class_name"])
        if sub_ing is not None:
            # This ingredient was in the substitution picker
            entry["is_satisfied"] = sub_ing.get("is_satisfied", False)
            # Find matching swap index
            ing_idx = sub_ingredients.index(sub_ing)
            if ing_idx in swaps:
                swap = swaps[ing_idx]
                entry["swapped"] = True
                entry["original_class"] = ri["class_name"]
                entry["class_name"] = swap["class_name"]
                entry["bottle_brand"] = swap["brand"]
                entry["bottle_label"] = swap["label"]
            else:
                entry["swapped"] = False
        else:
            # Commodity, garnish, or optional — pass through
            entry["is_satisfied"] = True
            entry["swapped"] = False
        preview_ingredients.append(entry)

    preview_ctx = {
        "recipe_id": recipe_id,
        "recipe_name": ctx_data["recipe_name"],
        "iba_category": ctx_data["iba_category"],
        "recipe": recipe,
        "preview_ingredients": preview_ingredients,
        "swap_count": len(swaps),
    }

    return templates.TemplateResponse(request, "_substitutions_preview.html", preview_ctx)
