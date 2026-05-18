# Mix/ML Frontend

Web UI for the mix-ml cocktail intelligence platform.
Separate HTTP service that calls the backend API and renders HTML via Jinja2 + HTMX.

## Stack

- **Python 3.11+** / FastAPI / Jinja2
- **HTMX 1.9** for client-side interactivity (CDN, no build step)
- **Tailwind CSS** via CDN (dev); precompiled `static/css/app.css` in prod
- **httpx** for backend HTTP calls
- **scipy + numpy** for hierarchical clustering (flavor map)
- **Plotly.js** for interactive 2D flavor map visualization (CDN) — *see note below*
- No Node, no bundler, no npm

### Plotly.js Exception

The **2D flavor map** uses Plotly.js (via CDN) for interactive scatter plot visualization with zoom/pan/click and color-mode toggle. This is the only client-side JavaScript library in the project (beyond HTMX).

**Why?** Plotting zoom/pan/click interactivity with dual-coloring modes requires event handling and dynamic recoloring that HTMX + pure SVG cannot support efficiently. Plotly.js solves this in ~15 lines of custom JS.

All data is pre-computed server-side (UMAP dimensionality reduction, Plotly figure JSON). Plotly.js is loaded only on `/inventory/flavor-map` (not on other pages, to avoid bloat).

## Features

- **Home** — cocktail grid with feasibility badges, category filtering via HTMX
- **Cocktail detail** — recipe breakdown with profile radar
- **Inventory** — bottle cards with expandable flavor profiles, grouped by family
- **Flavor map** — Two interactive views:
  - **Heatmap** — SVG matrix of pairwise flavor distances (hierarchical clustering)
  - **2D Map** — UMAP scatter plot with zoom/pan, color-toggle (cluster vs. family), click for bottle details
- **Substitutions** — per-cocktail ingredient analysis with strict/loose alternatives, preview modal with status badges
- **Shopping planner** — ILP-based multi-step purchase optimizer

## Local Development

Prerequisites: backend running on `localhost:8080` (via port-forward or direct).

```bash
cd frontend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Default BACKEND_URL is http://localhost:8080
uvicorn app.main:app --host 0.0.0.0 --port 3000 --reload
```

Open http://localhost:3000.

Override backend URL:
```bash
BACKEND_URL=http://172.25.144.1:8080 uvicorn app.main:app --port 3000 --reload
```

## Tests

```bash
cd frontend && source .venv/bin/activate
python -m pytest tests/ -v   # 80 tests
```

Tests mock the backend client — no live backend needed.

## Container Build

```bash
podman build -t mix-ml-frontend:latest frontend/
```

## Kubernetes Deployment

Manifests in `manifests/base/`:
- `frontend-deployment.yaml` — 2 replicas, probes on `/healthz` and `/readyz`
- `frontend-service.yaml` — ClusterIP port 8080
- `frontend-route.yaml` — OpenShift Route with TLS edge termination

CRC overlay (`manifests/overlays/crc/`) scales to 1 replica with reduced resources.

```bash
oc apply -k manifests/overlays/crc/
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BACKEND_URL` | `http://localhost:8080` | Base URL of the backend API |

## Startup Behavior

On startup, the frontend waits up to 30s for the backend health check,
then fetches all bottles with flavor profiles, computes the N×N flavor
distance matrix, runs hierarchical clustering (scipy average linkage),
renders the SVG heatmap, and caches it on `app.state`. 

Additionally, it builds a 2D UMAP projection of the flavor space and
prepares a Plotly scatter figure (JSON), cached on `app.state.flavor_map_2d`.
Both precomputations run once and are served instantly on subsequent requests.

If either precomputation fails (e.g., UMAP convergence, numba issue), the
affected feature shows a graceful error message; other features continue.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Home — cocktails you can make now |
| GET | `/cocktails/can-make-now` | Cocktail list (HTMX partial or full page) |
| GET | `/cocktails/{id}` | Cocktail detail page |
| GET | `/inventory` | Bottle inventory (Collection tab) |
| GET | `/inventory/{id}/profile` | Expanded bottle card (HTMX partial) |
| GET | `/inventory/{id}/collapse` | Collapsed bottle card (HTMX partial) |
| GET | `/inventory/flavor-map` | Flavor map (Heatmap & 2D Map tabs) |
| GET | `/inventory/flavor-map/regenerate` | Dev-only: recompute matrix & 2D map |
| GET | `/substitutions` | Substitution explorer |
| GET | `/substitutions/preview` | Recipe preview modal (HTMX partial) |
| GET | `/shopping` | Shopping planner |
| GET | `/shopping/optimize` | Run shopping optimization (HTMX partial) |
| GET | `/healthz` | Liveness probe (always 200) |
| GET | `/readyz` | Readiness probe (pings backend `/healthz`) |
