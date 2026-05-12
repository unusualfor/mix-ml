import logging
import re
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.client import fetch_cocktail_feasibility, fetch_recipe_detail
from app.templating import templates

logger = logging.getLogger(__name__)
router = APIRouter()

_METHOD_RE = re.compile(r"\b(shake|stir|build|blend|muddle)\b", re.IGNORECASE)


def _detect_method(method_text: str | None) -> str | None:
    if not method_text:
        return None
    m = _METHOD_RE.search(method_text)
    return m.group(1).capitalize() if m else None


def _merge_ingredients(recipe: dict, feasibility: dict) -> list[dict]:
    """Merge recipe ingredients (amount/unit) with feasibility (commodity/bottles)."""
    feas_by_name: dict[str, dict] = {}
    for ing in feasibility.get("ingredients", []):
        feas_by_name[ing["class_name"]] = ing

    merged = []
    for ing in recipe.get("ingredients", []):
        name = ing["class_name"]
        feas = feas_by_name.pop(name, {})
        merged.append({
            "class_name": name,
            "raw_name": ing.get("raw_name"),
            "amount": ing.get("amount"),
            "unit": ing.get("unit"),
            "is_optional": ing.get("is_optional", False),
            "is_garnish": ing.get("is_garnish", False),
            "is_commodity": feas.get("is_commodity", False),
            "alternative_group_id": ing.get("alternative_group_id"),
            "satisfied_by_bottles": feas.get("satisfied_by_bottles", []),
        })

    # Any feasibility-only ingredients (shouldn't happen, but be robust)
    for name, feas in feas_by_name.items():
        logger.warning("Ingredient %r in feasibility but not in recipe", name)
        merged.append({
            "class_name": name,
            "raw_name": None,
            "amount": None,
            "unit": None,
            "is_optional": feas.get("is_optional", False),
            "is_garnish": feas.get("is_garnish", False),
            "is_commodity": feas.get("is_commodity", False),
            "alternative_group_id": feas.get("alternative_group_id"),
            "satisfied_by_bottles": feas.get("satisfied_by_bottles", []),
        })

    return merged


def _group_alternatives(ingredients: list[dict]) -> list[dict | list[dict]]:
    """Return list where alt-group ingredients are grouped into sub-lists."""
    groups: dict[int, list[dict]] = {}
    result: list[dict | list[dict]] = []
    seen_groups: set[int] = set()

    for ing in ingredients:
        gid = ing.get("alternative_group_id")
        if gid is not None:
            groups.setdefault(gid, []).append(ing)
            if gid not in seen_groups:
                seen_groups.add(gid)
                result.append(groups[gid])  # reference, will grow
        else:
            result.append(ing)

    return result


_BACK_MAP = {
    "/shopping": ("/shopping", "Back to shopping planner"),
    "/inventory": ("/inventory", "Back to inventory"),
}
_DEFAULT_BACK = ("/", "Back to cocktails")


def _resolve_back(request: Request) -> tuple[str, str]:
    referer = request.headers.get("referer") or request.headers.get("hx-current-url") or ""
    path = urlparse(referer).path if referer else ""
    for prefix, back in _BACK_MAP.items():
        if path.startswith(prefix):
            return back
    return _DEFAULT_BACK


@router.get("/cocktail/{recipe_id}", response_class=HTMLResponse)
def cocktail_detail(request: Request, recipe_id: int):
    try:
        recipe = fetch_recipe_detail(recipe_id)
        feasibility = fetch_cocktail_feasibility(recipe_id)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            resp = templates.TemplateResponse(
                request, "_404.html", {"message": "Cocktail not found"},
            )
            resp.status_code = 404
            return resp
        raise
    except httpx.HTTPError:
        logger.exception("Backend call failed for recipe %s", recipe_id)
        resp = templates.TemplateResponse(
            request, "_404.html",
            {"message": "Cannot connect to the backend service right now."},
        )
        resp.status_code = 502
        return resp

    merged = _merge_ingredients(recipe, feasibility)
    grouped = _group_alternatives(merged)
    detected_method = _detect_method(recipe.get("method"))
    back_url, back_label = _resolve_back(request)

    ctx = {
        "recipe": recipe,
        "can_make": feasibility.get("can_make", False),
        "ingredients": grouped,
        "detected_method": detected_method,
        "back_url": back_url,
        "back_label": back_label,
    }

    is_htmx = request.headers.get("HX-Request") == "true"
    if is_htmx:
        return templates.TemplateResponse(
            request, "_cocktail_detail_content.html", ctx,
        )
    return templates.TemplateResponse(
        request, "cocktail_detail.html", ctx,
    )
