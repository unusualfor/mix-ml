import logging

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.client import fetch_cocktails_can_make_now
from app.templating import templates

logger = logging.getLogger(__name__)
router = APIRouter()


def _render_list(request: Request, category: str = "all", status: str = "can_make") -> str:
    """Fetch cocktails and render the card list partial."""
    try:
        data = fetch_cocktails_can_make_now(
            category if category != "all" else None,
            status=status,
        )
        items = data.get("items", [])
        error = None
    except httpx.HTTPError:
        logger.exception("Backend call failed")
        items = []
        error = "backend_down"

    return templates.TemplateResponse(
        request, "_cocktail_list.html",
        {"items": items, "error": error, "category": category, "status": status},
    )


@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    try:
        data = fetch_cocktails_can_make_now()
        items = data.get("items", [])
        error = None
    except httpx.HTTPError:
        logger.exception("Backend call failed")
        items = []
        error = "backend_down"

    return templates.TemplateResponse(
        request, "home.html",
        {"items": items, "error": error, "category": "all", "status": "can_make"},
    )


@router.get("/cocktails/can-make-now", response_class=HTMLResponse)
def cocktails_can_make_now(
    request: Request,
    category: str = "all",
    status: str = "can_make",
):
    is_htmx = request.headers.get("HX-Request") == "true"

    if is_htmx:
        return _render_list(request, category, status)

    # Full page fallback (direct browser navigation)
    try:
        data = fetch_cocktails_can_make_now(
            category if category != "all" else None,
            status=status,
        )
        items = data.get("items", [])
        error = None
    except httpx.HTTPError:
        logger.exception("Backend call failed")
        items = []
        error = "backend_down"

    return templates.TemplateResponse(
        request, "home.html",
        {"items": items, "error": error, "category": category, "status": status},
    )
