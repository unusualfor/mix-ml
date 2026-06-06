# Frontend Web UI

Jinja2 + HTMX + Plotly.js web interface for the mix-ml cocktail platform.

**For overview, quick start, and getting your own bottles working, see the [root README](../README.md).**

## Stack

- **Python 3.11+** / FastAPI / Jinja2
- **HTMX 1.9** (CDN) — interactive forms without page reload
- **Tailwind CSS** (CDN dev, precompiled prod)
- **Plotly.js** (CDN) — interactive 2D scatter plot on `/inventory/flavor-map`
- **SciPy** — UMAP dimensionality reduction, hierarchical clustering
- No build step, no JavaScript bundler, no npm

## Local Development

```bash
cd frontend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Backend must be running (see backend/README.md)
BACKEND_URL="http://localhost:8080" uvicorn app.main:app --port 3000 --reload
```

Open **http://localhost:3000**.

To override backend:
```bash
BACKEND_URL="http://192.168.x.x:8080" uvicorn app.main:app --port 3000 --reload
```

## Routes

| Path | Purpose |
|------|---------|
| `/` | Home — cocktails you can make now |
| `/iba` | Browse all 102 IBA recipes with detail view |
| `/cocktails/can-make-now` | Feasible recipes (same as home, HTMX-navigable) |
| `/cocktails/{id}` | Recipe detail with profile radar chart |
| `/inventory` | Bottle collection organized by family |
| `/inventory/flavor-map` | Interactive 2D scatter plot + heatmap of bottles |
| `/inventory/flavor-map?view=2d` | Force 2D Map tab |
| `/inventory/flavor-map?view=heatmap` | Force Heatmap tab |
| `/substitutions` | Per-recipe ingredient alternatives |
| `/shopping` | Multi-step ILP purchase optimizer |
| `/healthz` | Liveness probe (always 200) |
| `/readyz` | Readiness probe (pings backend `/healthz`) |

## Tests

```bash
pytest tests/ -v   # 80 tests, no backend required (mocked)
```

Tests mock the backend client, so a live API is not needed.

## Startup: What Happens

On server startup, the frontend:

1. Waits up to 30s for backend health check
2. Fetches all bottles with 16D flavor profiles
3. Computes N×N flavor distance matrix
4. Runs hierarchical clustering (SciPy average linkage) → renders SVG heatmap
5. Fits UMAP projection (16D → 2D)
6. Runs DBSCAN on 2D embedding to find clusters
7. Matches clusters with human impressions from `cluster_impressions.json`
8. Builds Plotly scatter figure JSON and caches it

Both precomputations run once at startup and are served instantly on subsequent requests.

If a computation fails (e.g., UMAP convergence, numba timeout), the affected feature shows a graceful error; other features work normally.

## 2D Flavor Map in Detail

The interactive scatter plot uses:

**UMAP parameters:**
- `n_neighbors=10` (auto-capped to dataset size - 1)
- `min_dist=0.3`
- `metric=euclidean`
- `random_state=42` (deterministic)

**DBSCAN parameters:**
- `eps=0.6` (tunable via the in-container `app._tools.calibrate` module)
- `min_samples=2`
- Outliers get individual cluster IDs (-1, -2, -3, ... -8 for 8 outliers)

**Cluster impressions** (`frontend/app/data/cluster_impressions.json`):
- Stored as JSON with bottle set compositions + human-written descriptions
- **Bind-mounted into the container** — edits don't require an image rebuild
- Loader uses an mtime-aware cache: new file content is picked up between requests, no process restart needed (`docker compose restart frontend` is only needed to clear the cached 2D map itself)
- Matched to live clusters via 75% overlap heuristic
- Auto-generated fallback for new/shifted clusters: `<Primary>-leaning · Signature notes: …` (the prefix is what the side panel renders as the cluster title, so unnamed clusters never fall back to a generic "Outlier" label)

**Coloring modes:**
- **Cluster**: ML-discovered DBSCAN groups (colorful palette)
- **Family**: Whiskey, Gin, Rum, etc. (14 distinct colors)

**Interactivity:**
- Hover to highlight cluster + show bottle name/brand
- Click to expand full flavor profile panel
- Zoom/pan with mouse wheel/drag (Plotly default)
- Toggle coloring mode with buttons

See root README [2D Flavor Map Calibration](../README.md#2d-flavor-map-calibration-detailed) for tuning after changing bottles, and [`scripts/add-bottle.sh`](../scripts/add-bottle.sh) for the one-command add-a-bottle pipeline.

## Heatmap

N×N hierarchical-clustered SVG matrix of pairwise flavor distances. Computed at startup, pre-rendered, instantly served.

Shows flavor "bridges" — bottles that link otherwise-distant families.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BACKEND_URL` | `http://localhost:8080` | Backend API base URL |

## Container Build

```bash
docker build -f frontend/Dockerfile -t mix-ml-frontend:latest frontend/
```

Image includes precompiled Tailwind CSS, reduced dependencies, and production-grade FastAPI settings.

## Kubernetes Deployment

Manifests in `manifests/base/`:
- `frontend-deployment.yaml` — 2 replicas, health probes on `/healthz` + `/readyz`
- `frontend-service.yaml` — ClusterIP port 8080
- `frontend-route.yaml` — OpenShift Route with TLS edge termination

CRC overlay scales to 1 replica with reduced memory limits.

## Architecture

Frontend talks to backend API via httpx (async HTTP client). All heavy computation (UMAP, clustering) happens server-side. Client-side JavaScript (Plotly.js) is minimal and used only for pan/zoom/click interactivity that HTML can't provide.

No server-side WebSocket, no polling. Each page load fetches fresh data from backend (cached by nginx in production).

---

See [root README](../README.md) for full project overview, quick start, 2D Map calibration, and how to add your own bottles.
