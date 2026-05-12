import logging

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.client import fetch_all_bottles, fetch_bottle_by_id
from app.services.flavor_matrix_builder import build_flavor_matrix
from app.services.flavor_matrix_renderer import render_flavor_matrix_svg
from app.templating import templates

logger = logging.getLogger(__name__)
router = APIRouter()

# Families pinned to the top, in this order; everything else alphabetical after.
_PINNED_FAMILIES = ["Whiskey", "Gin", "Bitter Italiano", "Vermouth", "Amaro"]

_GUSTATIVE_DIMS = [
    "sweet", "bitter", "sour", "citrusy", "fruity", "herbal",
    "floral", "spicy", "smoky", "vanilla", "woody", "minty",
    "earthy", "umami",
]
_STRUCTURAL_DIMS = ["body", "intensity"]


def _family_sort_key(family_name: str) -> tuple[int, str]:
    try:
        return (0, str(_PINNED_FAMILIES.index(family_name)))
    except ValueError:
        return (1, family_name)


def _group_by_family(items: list[dict]) -> list[dict]:
    """Group bottles by family_name, sorted with pinned families first."""
    families: dict[str, list[dict]] = {}
    for b in items:
        fname = b.get("family_name") or "Other"
        families.setdefault(fname, []).append(b)

    result = []
    for fname in sorted(families, key=_family_sort_key):
        bottles = sorted(families[fname], key=lambda b: (b.get("brand", ""), b.get("label") or ""))
        result.append({"name": fname, "count": len(bottles), "bottles": bottles})
    return result


def _build_profile_data(flavor_profile: dict | None) -> dict:
    """Split flavor profile into gustative (non-zero, desc) and structural lists."""
    if not flavor_profile:
        return {"gustative": [], "gustative_zero": [], "structural": []}

    gustative = []
    gustative_zero = []
    for dim in _GUSTATIVE_DIMS:
        val = flavor_profile.get(dim, 0)
        entry = {"name": dim, "value": val, "pct": val * 20}
        if val > 0:
            gustative.append(entry)
        else:
            gustative_zero.append(entry)
    gustative.sort(key=lambda d: -d["value"])

    structural = []
    for dim in _STRUCTURAL_DIMS:
        val = flavor_profile.get(dim, 0)
        structural.append({"name": dim, "value": val, "pct": val * 20})

    return {
        "gustative": gustative,
        "gustative_zero": gustative_zero,
        "structural": structural,
    }


def _fetch_and_group(filter_on_hand: bool | None) -> dict:
    data = fetch_all_bottles(filter_on_hand)
    items = data.get("items", [])
    families = _group_by_family(items)
    family_count = len(families)
    bottle_count = len(items)
    return {
        "families": families,
        "bottle_count": bottle_count,
        "family_count": family_count,
    }


@router.get("/inventory", response_class=HTMLResponse)
def inventory_page(request: Request, filter: str = "all"):
    filter_on_hand = {"on_hand": True, "not_on_hand": False}.get(filter)

    try:
        ctx = _fetch_and_group(filter_on_hand)
        ctx["filter"] = filter
        ctx["error"] = None
    except httpx.HTTPError:
        logger.exception("Backend call failed")
        ctx = {
            "families": [],
            "bottle_count": 0,
            "family_count": 0,
            "filter": filter,
            "error": "backend_down",
        }

    ctx["active_tab"] = "collection"

    is_htmx = request.headers.get("HX-Request") == "true"
    hx_target = request.headers.get("HX-Target", "")
    if is_htmx and hx_target in ("bottles-grid", "tab-content", ""):
        return templates.TemplateResponse(request, "_inventory_grid.html", ctx)
    return templates.TemplateResponse(request, "inventory.html", ctx)


def _flavor_map_ctx(request: Request) -> dict:
    """Build context dict for the flavor-map tab."""
    svg = getattr(request.app.state, "flavor_matrix_svg", None)
    matrix_data = getattr(request.app.state, "flavor_matrix_data", None)

    if svg is None or matrix_data is None:
        return {
            "active_tab": "flavor_map",
            "matrix_available": False,
            "bottle_count": 0,
            "family_count": 0,
        }

    # Derive bottle/family counts from cached data
    bottles = matrix_data.ordered_bottles
    families = {b.get("family_name", "Other") for b in bottles}

    return {
        "active_tab": "flavor_map",
        "matrix_available": True,
        "svg": svg,
        "clusters": matrix_data.clusters,
        "singleton_bottle_ids": matrix_data.singleton_bottle_ids,
        "singleton_bottles": [
            b for b in bottles if b["id"] in set(matrix_data.singleton_bottle_ids)
        ],
        "inter_cluster_pairs": matrix_data.inter_cluster_pairs,
        "generation_time": matrix_data.generation_time,
        "bottle_count": len(bottles),
        "family_count": len(families),
    }


@router.get("/inventory/flavor-map", response_class=HTMLResponse)
def flavor_map_page(request: Request):
    ctx = _flavor_map_ctx(request)

    is_htmx = request.headers.get("HX-Request") == "true"
    hx_target = request.headers.get("HX-Target", "")
    if is_htmx and hx_target == "tab-content":
        return templates.TemplateResponse(request, "_flavor_map_content.html", ctx)
    return templates.TemplateResponse(request, "flavor_map.html", ctx)


@router.get("/inventory/flavor-map/regenerate", response_class=HTMLResponse)
def flavor_map_regenerate(request: Request):
    """Dev-only: regenerate the flavor matrix without restarting."""
    from app.main import _generate_flavor_matrix
    _generate_flavor_matrix(request.app)
    ctx = _flavor_map_ctx(request)
    return templates.TemplateResponse(request, "flavor_map.html", ctx)


@router.get("/inventory/{bottle_id}", response_class=HTMLResponse)
def bottle_card_collapsed(request: Request, bottle_id: int):
    bottle = fetch_bottle_by_id(bottle_id)
    if bottle is None:
        return HTMLResponse("<p class='text-sm text-slate-500'>Bottle not found.</p>", status_code=404)
    return templates.TemplateResponse(
        request, "_bottle_card.html", {"bottle": bottle},
    )


@router.get("/inventory/{bottle_id}/profile", response_class=HTMLResponse)
def bottle_card_expanded(request: Request, bottle_id: int):
    bottle = fetch_bottle_by_id(bottle_id)
    if bottle is None:
        return HTMLResponse("<p class='text-sm text-slate-500'>Bottle not found.</p>", status_code=404)
    profile = _build_profile_data(bottle.get("flavor_profile"))
    return templates.TemplateResponse(
        request, "_bottle_card_expanded.html",
        {"bottle": bottle, "profile": profile},
    )
