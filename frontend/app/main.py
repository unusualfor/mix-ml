from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routers import detail, health, home, inventory, shopping, substitutions

_BASE = Path(__file__).resolve().parent


def _generate_flavor_matrix(app: FastAPI) -> None:
    """Build flavor matrix from backend bottles and cache on app.state."""
    import logging
    import time

    import httpx

    from app.client import fetch_all_bottles
    from app.services.flavor_matrix_builder import build_flavor_matrix
    from app.services.flavor_matrix_renderer import render_flavor_matrix_svg

    logger = logging.getLogger("mix-ml.startup")

    # Wait for backend readiness (up to 30 s)
    from app.config import settings

    deadline = time.monotonic() + 30
    backend_up = False
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(f"{settings.backend_url}/healthz", timeout=3.0)
            if resp.status_code == 200:
                backend_up = True
                break
        except httpx.HTTPError:
            pass
        time.sleep(1)

    if not backend_up:
        logger.warning("Backend not reachable after 30 s — flavor matrix skipped")
        app.state.flavor_matrix_svg = None
        app.state.flavor_matrix_data = None
        return

    t0 = time.monotonic()
    try:
        data = fetch_all_bottles()
        items = data.get("items", [])
        matrix_data = build_flavor_matrix(items)
        svg = render_flavor_matrix_svg(matrix_data)
        app.state.flavor_matrix_svg = svg
        app.state.flavor_matrix_data = matrix_data
        elapsed = int((time.monotonic() - t0) * 1000)
        logger.info(
            "Flavor matrix generated: %d bottles, %d clusters, took %d ms",
            len(matrix_data.ordered_bottles),
            len(matrix_data.clusters),
            elapsed,
        )
    except Exception:
        logger.exception("Flavor matrix generation failed")
        app.state.flavor_matrix_svg = None
        app.state.flavor_matrix_data = None


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        _generate_flavor_matrix(app)
        yield

    app = FastAPI(title="mix-ml frontend", docs_url=None, redoc_url=None, lifespan=lifespan)

    app.mount(
        "/static",
        StaticFiles(directory=_BASE / "static"),
        name="static",
    )

    app.include_router(health.router)
    app.include_router(home.router)
    app.include_router(detail.router)
    app.include_router(inventory.router)
    app.include_router(shopping.router)
    app.include_router(substitutions.router)

    return app


app = create_app()
