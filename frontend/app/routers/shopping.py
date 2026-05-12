import logging

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.client import fetch_optimize_shopping
from app.templating import templates

logger = logging.getLogger(__name__)
router = APIRouter()

WEIGHT_MAP = {0: 0.0, 1: 0.5, 2: 1.0, 3: 1.5, 4: 2.0}
WEIGHT_LABELS = {
    0: "ignore",
    1: "low",
    2: "normal",
    3: "prefer",
    4: "strong prefer",
}

_DEFAULTS = {"budget": 3, "wu": 2, "wc": 2, "wn": 2}


def _parse_params(
    budget: int = _DEFAULTS["budget"],
    wu: int = _DEFAULTS["wu"],
    wc: int = _DEFAULTS["wc"],
    wn: int = _DEFAULTS["wn"],
    reset: bool = False,
) -> dict:
    if reset:
        budget = _DEFAULTS["budget"]
        wu = _DEFAULTS["wu"]
        wc = _DEFAULTS["wc"]
        wn = _DEFAULTS["wn"]
    budget = max(1, min(10, budget))
    wu = max(0, min(4, wu))
    wc = max(0, min(4, wc))
    wn = max(0, min(4, wn))
    return {
        "budget": budget,
        "wu": wu, "wc": wc, "wn": wn,
        "weight_unforgettable": WEIGHT_MAP[wu],
        "weight_contemporary": WEIGHT_MAP[wc],
        "weight_new_era": WEIGHT_MAP[wn],
        "wu_label": WEIGHT_LABELS[wu],
        "wc_label": WEIGHT_LABELS[wc],
        "wn_label": WEIGHT_LABELS[wn],
    }


def _build_results_ctx(params: dict) -> dict:
    """Call backend and build template context for results partial."""
    try:
        data = fetch_optimize_shopping(
            budget=params["budget"],
            weight_unforgettable=params["weight_unforgettable"],
            weight_contemporary=params["weight_contemporary"],
            weight_new_era=params["weight_new_era"],
        )
        error = None
    except httpx.HTTPError:
        logger.exception("Backend shopping call failed")
        data = None
        error = "backend_error"

    if data is None:
        return {"error": error, "data": None, "params": params}

    solution = data.get("solution", {})
    explanation = data.get("explanation", {})
    current = data.get("current_state", {})

    purchases = solution.get("recommended_purchases", [])
    marginal = {
        m["class_name"]: m
        for m in explanation.get("purchases_marginal_value", [])
    }
    for p in purchases:
        mv = marginal.get(p["class_name"], {})
        p["unlocks"] = mv.get("incremental_recipes_unlocked", 0)

    newly_feasible = explanation.get("newly_feasible_recipes", [])
    by_category: dict[str, list[dict]] = {}
    for r in newly_feasible:
        cat = r.get("iba_category", "other")
        by_category.setdefault(cat, []).append(r)
    cat_order = ["unforgettable", "contemporary", "new_era"]
    grouped_recipes = [
        {"category": c, "recipes": by_category[c]}
        for c in cat_order if c in by_category
    ]

    return {
        "error": None,
        "params": params,
        "delta": solution.get("delta", 0),
        "feasible_before": current.get("feasible_recipes", 0),
        "feasible_after": solution.get("feasible_recipes_after", 0),
        "is_optimal": solution.get("is_optimal", True),
        "computation_time_ms": solution.get("computation_time_ms", 0),
        "purchases": purchases,
        "grouped_recipes": grouped_recipes,
        "newly_feasible_count": len(newly_feasible),
    }


@router.get("/shopping", response_class=HTMLResponse)
def shopping_page(request: Request):
    params = _parse_params()
    ctx = _build_results_ctx(params)
    return templates.TemplateResponse(request, "shopping.html", ctx)


@router.get("/shopping/results", response_class=HTMLResponse)
def shopping_results(
    request: Request,
    budget: int = _DEFAULTS["budget"],
    wu: int = _DEFAULTS["wu"],
    wc: int = _DEFAULTS["wc"],
    wn: int = _DEFAULTS["wn"],
    reset: bool = False,
):
    params = _parse_params(budget, wu, wc, wn, reset)
    ctx = _build_results_ctx(params)

    is_htmx = request.headers.get("HX-Request") == "true"
    if is_htmx:
        return templates.TemplateResponse(request, "_shopping_results.html", ctx)
    # Full page fallback
    return templates.TemplateResponse(request, "shopping.html", ctx)
