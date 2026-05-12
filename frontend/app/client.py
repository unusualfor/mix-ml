import httpx

from app.config import settings

_client: httpx.Client | None = None


def _get_client() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(base_url=settings.backend_url, timeout=10.0)
    return _client


def fetch_cocktails_can_make_now(
    category: str | None = None,
    status: str = "can_make",
) -> dict:
    params: dict[str, str] = {"status": status}
    if category and category != "all":
        params["category"] = category
    resp = _get_client().get("/api/cocktails/can-make-now", params=params)
    resp.raise_for_status()
    return resp.json()


def ping_backend() -> bool:
    try:
        resp = _get_client().get("/healthz", timeout=3.0)
        return resp.status_code == 200
    except httpx.HTTPError:
        return False


def fetch_recipe_detail(recipe_id: int) -> dict:
    resp = _get_client().get(f"/api/recipes/{recipe_id}")
    resp.raise_for_status()
    return resp.json()


def fetch_cocktail_feasibility(recipe_id: int) -> dict:
    resp = _get_client().get(f"/api/cocktails/{recipe_id}/feasibility")
    resp.raise_for_status()
    return resp.json()


def fetch_all_bottles(filter_on_hand: bool | None = None) -> dict:
    params: dict[str, str] = {"limit": "200"}
    if filter_on_hand is not None:
        params["on_hand"] = str(filter_on_hand).lower()
    resp = _get_client().get("/api/bottles", params=params)
    resp.raise_for_status()
    return resp.json()


def fetch_bottle_by_id(bottle_id: int) -> dict | None:
    data = fetch_all_bottles()
    for b in data.get("items", []):
        if b["id"] == bottle_id:
            return b
    return None


def fetch_optimize_shopping(
    budget: int = 3,
    weight_unforgettable: float = 1.0,
    weight_contemporary: float = 1.0,
    weight_new_era: float = 1.0,
    explain: bool = True,
) -> dict:
    params: dict[str, str] = {
        "budget": str(budget),
        "weight_unforgettable": str(weight_unforgettable),
        "weight_contemporary": str(weight_contemporary),
        "weight_new_era": str(weight_new_era),
    }
    if explain:
        params["explain"] = "true"
    resp = _get_client().get("/api/bottles/optimize-shopping", params=params)
    resp.raise_for_status()
    return resp.json()


def fetch_recipe_substitutions(
    recipe_id: int,
    tier: str = "both",
    include_satisfied: bool = False,
) -> dict:
    params: dict[str, str] = {
        "tier": tier,
        "include_satisfied": str(include_satisfied).lower(),
    }
    resp = _get_client().get(
        f"/api/recipes/{recipe_id}/substitutions", params=params,
    )
    resp.raise_for_status()
    return resp.json()
