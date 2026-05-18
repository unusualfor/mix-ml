# Mix/ML — ML-assisted bar intelligence platform

A data-driven cocktail platform with inventory management, interactive flavor mapping, and AI-assisted optimization. Built on 102 official IBA recipes with support for custom bottle collections.

## Key Features

- **2D Flavor Map** — Interactive scatter plot with UMAP dimensionality reduction and DBSCAN clustering. Hover to explore, toggle between cluster and family coloring.
- **Heatmap** — N×N flavor distance matrix with hierarchical clustering for quick visual similarity analysis.
- **Cocktail Feasibility** — Know which drinks you can make right now from your current inventory.
- **Smart Substitutions** — When you're missing an ingredient, find the closest alternative from your bottles ranked by flavor similarity.
- **Shopping Optimizer** — Multi-step ILP-based planner: given a budget of K bottles, find the optimal purchase to unlock the most new recipes.
- **Inventory Management** — Organize your bottles by family, view expanded flavor profiles, search by flavor dimension.

## Architecture

```
┌──────────────────────────────────────────┐
│  Frontend (FastAPI + HTMX + Jinja2)      │
│  Port 3000 | 2D Map · Inventory · IBA    │
└────────────────┬─────────────────────────┘
                 │ HTTP
┌────────────────▼─────────────────────────┐
│  Backend (FastAPI + SQLAlchemy)          │
│  Port 8080 | REST API · Flavor Distance  │
└────────────────┬─────────────────────────┘
                 │ SQL
┌────────────────▼─────────────────────────┐
│  PostgreSQL 16                           │
│  102 IBA recipes + Your bottle inventory │
└──────────────────────────────────────────┘
```

## Quick Start

### Option 1: Docker Compose (simplest)

```bash
docker compose up -d
```

This starts:
- **Frontend**: http://localhost:3000
- **Backend**: http://localhost:8080  
- **PostgreSQL**: Automatically seeded with IBA recipes + default bottles

To rebuild after code changes:
```bash
docker compose up -d --build
```

To reset data and reseed:
```bash
docker compose down -v && docker compose up -d
```

### Option 2: Local Development

Prerequisites: Python 3.11+, PostgreSQL 16 running with `db/seed.sql` loaded.

```bash
# Backend (terminal 1)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
export DATABASE_URL="postgresql+psycopg://cocktailuser:cocktail@localhost:5432/cocktails"
uvicorn app.main:app --port 8080 --reload

# Frontend (terminal 2)
cd frontend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
BACKEND_URL="http://localhost:8080" uvicorn app.main:app --port 3000 --reload
```

Backend API docs: http://localhost:8080/docs

### Option 3: OpenShift Local (CRC) with GitOps

For production-grade deployment with ArgoCD, see [OpenShift GitOps Setup](#openshift-gitops-setup-advanced) below.

## Getting Started With Your Own Bottles

This repo comes with ~42 default bottles. To adapt it to your personal collection:

### 1. Define Your Bottle Inventory

Edit `scripts/data/bottles_seed.json` with your bottles:

```json
[
  {
    "brand": "Talisker",
    "label": "10 Year Old",
    "family": "Whiskey",
    "flavor_profile": {
      "sweet": 1,
      "bitter": 3,
      "sour": 0,
      "citrusy": 1,
      "fruity": 2,
      "herbal": 1,
      "floral": 0,
      "spicy": 2,
      "smoky": 4,
      "vanilla": 1,
      "woody": 2,
      "minty": 1,
      "earthy": 1,
      "umami": 0,
      "body": 4,
      "intensity": 4
    },
    "on_hand": true
  }
]
```

Each `flavor_profile` value is 0–5 (0 = not present, 5 = dominant).

### 2. Generate Database Seed

```bash
cd scripts
python generate_seed_sql.py data/bottles_seed.json data/iba_cocktails_normalized.json
```

This outputs `seed.sql` with both your bottles and the 102 IBA recipes.

### 3. Update the Database

For Docker:
```bash
cp scripts/seed.sql db/seed.sql
docker compose down -v && docker compose up -d
```

For local dev:
```bash
psql -U cocktailuser -d cocktails -a -f scripts/seed.sql
```

### 4. Calibrate the 2D Flavor Map Impressions (Optional)

When you change your bottle collection significantly, the UMAP clustering may shift. To keep cluster impressions accurate:

```bash
# Regenerate cluster compositions with your live backend
python scripts/calibrate_clusters.py --backend-url http://localhost:8080 --write

# Edit cluster_impressions.json to replace "TODO" placeholders with real descriptions
# Then rebuild frontend
docker compose up -d --build frontend
```

For details, see [2D Flavor Map Calibration](#2d-flavor-map-calibration-detailed).

## Features in Detail

### 2D Flavor Map

The crown jewel: a zoomable, pannable scatter plot of your entire bottle collection in 2D flavor space.

**What it does:**
- **UMAP projection**: Reduces your 16-dimensional flavor profiles to 2D while preserving flavor neighborhoods
- **DBSCAN clustering**: Automatically groups similar bottles
- **Dual coloring**: Toggle between "Cluster" view (ML-discovered groups) and "Family" view (whiskey, gin, rum, etc.)
- **Interactive detail**: Hover bottles to see names/brands, click to expand full flavor profile
- **Impression summaries**: Each cluster has a human-written explanation of why those bottles cluster together

**Technical details:**
- UMAP parameters: `n_neighbors=10`, `min_dist=0.3`, `metric=euclidean`
- DBSCAN parameters: `eps=0.6`, `min_samples=2` (tunable, see calibration)
- Plotly.js for rendering (client-side pan/zoom/click)
- Cluster impressions stored in `frontend/app/data/cluster_impressions.json`

### Heatmap

An N×N hierarchical-clustered flavor distance matrix. Fast pre-computed at startup, useful for finding flavor "bridges" between distant bottle families.

### Inventory Management

Organized bottle browser with:
- Family-based grouping (Whiskey, Gin, Amaro, etc.)
- Expandable flavor profiles (all 16 dimensions visible)
- On-hand/out-of-stock toggle
- Search by brand or label

### Cocktail Feasibility

Shows which of the 102 IBA cocktails you can make **right now** with your current inventory. Badges show recipe category (Unforgettable / Contemporary / New Era). Click to see ingredients and any missing items.

### Substitutions

For any cocktail you can't make, get alternative suggestions ranked by flavor distance. Choose between:
- **Strict**: Same family, flavor distance ≤ 0.25
- **Loose**: Cross-family, flavor distance ≤ 0.20
- **Both**: See all options

### Shopping Optimizer

Given a budget (1–15 bottles), an integer linear programming solver finds the purchase set that maximizes the count of newly-feasible recipes. Solver respects recipe category weights (Unforgettables weighted higher).

## API Endpoints (Overview)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Home — cocktails you can make now |
| GET | `/inventory` | Bottle inventory with optional flavor-map view |
| GET | `/inventory/flavor-map` | Interactive 2D scatter plot + heatmap |
| GET | `/cocktails/can-make-now` | Feasible recipe list |
| GET | `/cocktails/{id}` | Recipe detail with profile radar |
| GET | `/substitutions` | Per-recipe ingredient alternatives |
| GET | `/shopping` | Multi-step purchase optimizer |
| GET | `/iba` | Browse all 102 IBA recipes |

For the full backend REST API:

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/bottles` | Your bottle inventory (JSON) |
| GET | `/api/recipes` | IBA recipes with `?category=` filter |
| GET | `/api/cocktails/can-make-now` | Feasible recipe IDs + names |
| GET | `/api/flavor/distance?bottle_a=X&bottle_b=Y` | Flavor distance breakdown |
| GET | `/api/flavor/similar-bottles?bottle_id=X` | Ranked neighbors |
| GET | `/api/cocktails/{id}/substitutions` | Per-recipe alternatives |
| GET | `/api/bottles/optimize-shopping?budget=K` | ILP K-bottle purchase plan |

Full interactive docs at http://localhost:8080/docs (running backend required).

## Testing

```bash
# Backend (104 tests)
cd backend && pytest tests/ -v

# Frontend (80 tests, no backend required)
cd frontend && pytest tests/ -v

# CI/CD validation (OpenShift only, requires CRC)
bash tests/test_full_gitops.sh
```

## Component Details

### Backend (`backend/`)

FastAPI REST API with SQLAlchemy ORM. Provides:
- Bottle inventory CRUD
- IBA recipe database
- Flavor distance computation (weighted Euclidean, gustative + structural)
- Feasibility checking (recursive ingredient satisfaction)
- Substitution ranking
- ILP-based shopping optimization (OR-Tools CP-SAT solver)

Setup: `backend/README.md`

### Frontend (`frontend/`)

FastAPI + Jinja2 + HTMX web UI. No JavaScript bundler, no Node. 

Stack:
- **Templating**: Jinja2 server-side rendering
- **Interactivity**: HTMX (CDN) for form submission without page reload
- **Styling**: Tailwind CSS (CDN dev, precompiled CSS prod)
- **2D Map**: Plotly.js (CDN) for interactive scatter plot
- **Clustering**: SciPy (UMAP + DBSCAN server-side)

Setup: `frontend/README.md`

### Database (`db/`)

PostgreSQL 16 schema with:
- `recipes` — 102 IBA cocktails
- `recipe_ingredients` — ingredients per recipe (with amounts/units)
- `bottles` — your personal inventory
- `bottle_flavors` — 16-dimensional flavor profiles
- `ingredient_classes` — taxonomy (spirits, bitters, juices, etc.)
- `is_commodity` flag for assumed-available ingredients

Database schema is generated by `generate_seed_sql.py`.

## Advanced

### OpenShift GitOps Setup (Advanced)

For production deployment on Red Hat OpenShift Local (CRC):

**Prerequisites:**
- OpenShift Local (CRC) running (~16 GB RAM)
- `oc` CLI logged in as `kubeadmin`
- GitHub PAT with `repo` + `write:packages` scope

**Setup:**
```bash
export POSTGRES_PASSWORD=$(openssl rand -base64 24)
export POSTGRES_ADMIN_PASSWORD=$(openssl rand -base64 24)
export GITHUB_USERNAME=<your-github-username>
export GITHUB_TOKEN=<your-ghp-token>

bash scripts/setup-secrets.sh
bash scripts/bootstrap-gitops.sh
bash scripts/bootstrap-ci.sh          # optional: for automated image builds
bash scripts/setup-ci-secrets.sh      # optional
```

The system will deploy:
- ArgoCD watching `manifests/overlays/crc/`
- Tekton pipelines for automated backend/frontend image builds
- Postgres 16 with automatic seeding
- Backend and frontend services behind OpenShift Routes

Full details: [Deployment & GitOps](#openshift-gitops-detailed) below.

### 2D Flavor Map Calibration (Detailed)

When you add/remove many bottles, UMAP and DBSCAN may discover different clusters. Impressions are calibrated to a specific bottle set via a 75% overlap matching heuristic.

**Workflow:**

1. Update `scripts/data/bottles_seed.json` with new bottles
2. Generate new seed:
   ```bash
   cd scripts && python generate_seed_sql.py data/bottles_seed.json
   cp seed.sql ../db/seed.sql
   ```
3. Reseed the database:
   ```bash
   docker compose down -v && docker compose up -d
   ```
4. Wait for backend to initialize (30s), then calibrate:
   ```bash
   python scripts/calibrate_clusters.py --backend-url http://localhost:8080 --write
   ```
5. Review `frontend/app/data/cluster_impressions.json` — edit TODO lines with real descriptions
6. Rebuild frontend:
   ```bash
   docker compose up -d --build frontend
   ```

**Tuning DBSCAN:**

If clustering looks wrong, adjust `eps`:
```bash
python scripts/calibrate_clusters.py --eps 0.7 --backend-url http://localhost:8080 --write
```

- Larger `eps` → fewer, larger clusters
- Smaller `eps` → more, tighter clusters
- Typical range for 30–80 bottles: 0.4–0.8
- Typical UMAP coordinate range: x ≈ 5 units, y ≈ 6 units

### Scraper & Analyzer (Advanced)

Tools for building the IBA recipe database from scratch.

**Scraper** (`scripts/scrape_iba.py`):
```bash
cd scripts && python scrape_iba.py
```

Downloads all 102 recipes from [iba-world.com](https://iba-world.com), parses ingredients and methods, outputs `data/iba_cocktails.json`.

**Analyzer** (`scripts/analyze_iba.py`):
```bash
cd scripts && python analyze_iba.py data/iba_cocktails.json
```

Generates reports:
- `report_ingredient_frequency.csv` — ingredient frequency + recipe lists
- `report_unit_inventory.csv` — units of measure + examples
- `report_ingredient_clusters.txt` — name-similarity groups (merge candidates)
- `report_summary.md` — overview (categories, top-20 ingredients, techniques)

### OpenShift GitOps Detailed

The official deployment uses ArgoCD to watch this repository and manage cluster state.

**Architecture:**
```
Developer
  ↓ (git push)
GitHub repo (main branch)
  ↓ (polled by)
ArgoCD (openshift-gitops)
  ├→ Tekton Pipelines (mix-ml-ci namespace) — build/push images
  ├→ Kustomize overlays (manifests/overlays/crc/)
  ↓
Kubernetes cluster (mix-ml namespace)
  ├ Postgres 16 (persistent storage)
  ├ Backend FastAPI
  └ Frontend HTMX+Jinja2
```

**Key decisions:**
- **Manifest-driven**: Cluster state fully defined in Git. No `oc apply` outside bootstrap.
- **Immutable tags**: Every build gets `git-<short-sha>`. Rollback is a Git revert.
- **Manual sync**: Human reviews diff in ArgoCD UI before deploying. (Can be auto-enabled in `Application` spec.)
- **Seeding automation**: ArgoCD PostSync hook runs `db/seed.sql` on every sync — idempotent.

**Daily workflows:**

*Backend change:*
```bash
# 1. Edit code, commit, push
# 2. Trigger build (CRC only)
bash scripts/build-backend.sh

# 3. ArgoCD UI → Refresh → Sync
# 4. Verify
oc get pods -n mix-ml -l app.kubernetes.io/name=backend
```

*Frontend change:* Same steps, use `bash scripts/build-frontend.sh`.

*Manifest change (env var, replicas, etc.):*
```bash
# 1. Edit manifests/base/*.yaml
# 2. Commit, push
# 3. ArgoCD UI → Refresh → Sync
```

*Rollback:*
```bash
git revert <commit-sha>
git push
# ArgoCD UI → Refresh → Sync
```

*Update bottle seed data:*
```bash
# 1. Edit scripts/data/bottles_seed.json
# 2. Regenerate seed
cd scripts && python generate_seed_sql.py data/bottles_seed.json
cp seed.sql ../db/seed.sql

# 3. Commit, push
# 4. ArgoCD UI → Refresh → Sync
# (PostSync hook re-seeds automatically)
```

### CI/CD Pipelines (Advanced)

Tekton pipelines in `mix-ml-ci` namespace build and push container images.

**Pipeline DAG:**
```
git-clone → compute-image-tag ─┐
         → lint-and-test ──────┼→ build-and-push → update-manifest
                               │     (buildah)
```

1. Clones repo
2. Lints (ruff) and tests (pytest)
3. Builds image with Buildah, pushes to ghcr.io with tags: `git-<short-sha>` + `latest`
4. Commits manifest update (Kustomize image override) to `main`
5. ArgoCD detects and shows OutOfSync

**Trigger:**
```bash
bash scripts/build-backend.sh     # Backend only
bash scripts/build-frontend.sh    # Frontend only
bash scripts/build-all.sh         # Both in parallel
```

**Watch:**
```bash
tkn pipelinerun list -n mix-ml-ci
tkn pipelinerun logs <name> -f -n mix-ml-ci
```

**Troubleshoot:**
| Issue | Fix |
|-------|-----|
| Auth error on push | Re-run `bash scripts/setup-ci-secrets.sh` |
| Git push fails | GitHub PAT expired or missing `repo` scope |
| Tests timeout | CRC needs more resources (~16GB RAM) |

See `tests/test_backend_ci.sh` and `tests/test_frontend_ci.sh` for validation.

### Manifests Structure

```
manifests/
├── operators/          # Red Hat GitOps + Pipelines subscriptions
├── argocd/             # ArgoCD Application CR
├── base/               # Base Kustomize components
│   ├── namespace.yaml
│   ├── postgres-*.yaml
│   ├── backend-*.yaml
│   ├── frontend-*.yaml
│   └── seed.sql
└── overlays/crc/       # CRC-specific resource limits + patches
```

Kustomize paths:
- Base: `manifests/base/kustomization.yaml`
- CRC overlay: `manifests/overlays/crc/kustomization.yaml`
- ArgoCD watches: `manifests/overlays/crc/` on `main` branch

## Project Structure

```
mix-ml/
├── README.md                          # This file
├── backend/                           # FastAPI REST API
│   ├── app/
│   │   ├── models.py                  # SQLAlchemy ORM
│   │   ├── queries.py                 # Database queries
│   │   ├── services/                  # Business logic
│   │   └── routers/                   # API endpoints
│   ├── tests/                         # 104 unit/integration tests
│   └── pyproject.toml
├── frontend/                          # HTMX web UI
│   ├── app/
│   │   ├── routers/                   # Page routes
│   │   ├── services/                  # UMAP, clustering, optimization
│   │   ├── templates/                 # Jinja2 HTML
│   │   ├── static/                    # CSS, favicon, images
│   │   └── data/
│   │       └── cluster_impressions.json # Human-written cluster descriptions
│   ├── tests/                         # 80 unit/integration tests
│   └── pyproject.toml
├── db/                                # Database schema
│   └── seed.sql                       # IBA recipes + default bottles
├── scripts/                           # Offline tools
│   ├── generate_seed_sql.py           # Build seed.sql from JSON
│   ├── calibrate_clusters.py          # Tune DBSCAN, update impressions
│   ├── scrape_iba.py                  # Download IBA recipes
│   ├── analyze_iba.py                 # Generate reports
│   ├── data/
│   │   ├── bottles_seed.json          # Your bottle inventory
│   │   └── iba_cocktails_normalized.json # Normalized recipe JSON
│   └── requirements-scripts.txt       # scipy, numpy for UMAP
├── manifests/                         # Kubernetes + ArgoCD
│   ├── base/
│   ├── overlays/crc/
│   ├── argocd/
│   └── operators/
├── tests/                             # Integration test scripts
│   ├── test_backend_ci.sh
│   ├── test_frontend_ci.sh
│   ├── test_gitops_setup.sh
│   └── test_full_gitops.sh
├── docker-compose.yaml                # Production image versions
├── compose.build.yaml                 # Local dev overrides (exposes ports)
└── .gitignore                         # Excludes .venv, .env, outputs
```

## Common Questions

**Q: Can I use this with a different set of cocktails?**
A: Yes. The scraper/analyzer pipeline works with any recipe collection. Update `scripts/data/iba_cocktails_normalized.json` and rebuild the seed.

**Q: Do I need OpenShift?**
A: No. Docker Compose is fully functional (simplest for most users). OpenShift is optional for production-grade GitOps workflows.

**Q: Can I customize flavor dimensions?**
A: The API currently hardcodes 16 dimensions (14 gustative + 2 structural). Adding/removing dimensions requires schema migration + frontend updates.

**Q: How do I add new bottles?**
A: Edit `scripts/data/bottles_seed.json`, regenerate seed.sql, reseed DB. No code changes needed.

**Q: What if my cluster impressions are stale after adding bottles?**
A: Run `calibrate_clusters.py --write` to auto-match with 75% overlap heuristic and flag new clusters with TODO.

## License & Attribution

IBA cocktail data sourced from [iba-world.com](https://iba-world.com).

Flavor profiles, bottle additions, and optimizations are author's own.

---

**Last updated:** May 2026  
**Latest version:** v1.3.9
