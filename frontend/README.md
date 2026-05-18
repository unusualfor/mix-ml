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

## 2D Flavor Map: Cluster Impressions

The 2D flavor map uses UMAP for dimensionality reduction and **DBSCAN** for
visual clustering on the 2D embedding. Each cluster and outlier gets a
hand-written "impression" — a short paragraph explaining *why* those bottles
group together (or don't).

### The Problem

Impressions are **static text tied to a specific bottle collection**. When you
add/remove bottles, UMAP coordinates shift and DBSCAN may produce different
clusters. The 75% overlap matching provides resilience against minor changes
(1-2 bottles added to a cluster), but large inventory changes will trigger
fallback to auto-generated impressions (bland "Top notes: X, Y, Z" text).

### How It Works

1. **Data file**: `frontend/app/data/cluster_impressions.json`
   - Contains cluster compositions (bottle lists) and their impressions
   - Contains per-bottle outlier explanations
   - Loaded at module import time

2. **Matching logic** (`flavor_map_2d_builder.py`):
   - For each DBSCAN cluster: find the entry in `cluster_impressions.json`
     whose bottle set has ≥75% overlap with the actual cluster
   - For outliers: exact match on `(brand, label)` key
   - Fallback: auto-generate from mean flavor profile

3. **Calibration script**: `scripts/calibrate_clusters.py`
   - Runs UMAP + DBSCAN against the live backend API
   - Outputs cluster compositions as JSON
   - Preserves existing impressions where overlap ≥75%
   - Marks new/changed clusters with `TODO` placeholders

### Workflow After Changing Your Inventory

```bash
# 1. Make sure backend is running with updated bottles
docker compose up -d backend

# 2. Run calibration to see new clusters
python scripts/calibrate_clusters.py --backend-url http://localhost:8080

# 3. Review output — check for TODO placeholders and shifted clusters.
#    Adjust eps if clusters look wrong:
python scripts/calibrate_clusters.py --eps 0.7

# 4. Once satisfied, write the file (preserves existing impressions):
python scripts/calibrate_clusters.py --write

# 5. Edit frontend/app/data/cluster_impressions.json
#    Replace any TODO lines with real impressions.

# 6. Rebuild frontend
docker compose up -d --build frontend
```

### For New Users Cloning This Repo

If you import a completely different bottle collection:

1. The 2D map will still render correctly (UMAP + DBSCAN work on any data)
2. All impressions will be auto-generated (functional but generic)
3. Run `scripts/calibrate_clusters.py --write` to generate a template
4. Write your own impressions in `cluster_impressions.json`

### DBSCAN Parameters

| Parameter | Default | Effect |
|-----------|---------|--------|
| `eps` | 0.6 | Neighborhood radius in UMAP 2D space. Larger = fewer clusters. Range [0.4–0.8] for typical collections of 30–80 bottles. |
| `min_samples` | 2 | Minimum points to form a cluster. 2 means any pair of close bottles forms a cluster. |

Typical UMAP coordinate range for ~40 bottles: x≈5, y≈6 units.

### Alternatives Considered

- **LLM-generated impressions at startup**: Would require an API key, adds
  latency, and produces inconsistent prose across restarts. Ruled out.
- **Pure auto-generation**: The fallback already does this. Works for
  structure but lacks the editorial voice that makes impressions interesting.
- **User-editable via UI**: Would need auth + persistence layer. Out of scope
  for this project's philosophy (data lives in files, not databases).
