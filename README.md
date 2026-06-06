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

The base `compose.yaml` joins backend and frontend to the external `caddy` network (used in production behind a reverse proxy) and does not publish ports. For local development you'll usually want to layer `compose.build.yaml` on top, which exposes `127.0.0.1:3000` (frontend) and `127.0.0.1:8080` (backend) and builds from source:

```bash
docker compose -f compose.yaml -f compose.build.yaml up -d --build
```

This starts:
- **Frontend**: http://localhost:3000
- **Backend**: http://localhost:8080
- **PostgreSQL**: Automatically seeded with IBA recipes + default bottles (initdb hook on `db/seed.sql`)

Production-style run (pull images from ghcr.io, no local build, expects caddy in front):

```bash
docker compose up -d
```

To rebuild after code changes:
```bash
docker compose -f compose.yaml -f compose.build.yaml up -d --build
```

To reset data and reseed (wipes the `pgdata` volume):
```bash
docker compose down -v && docker compose up -d
```

For adding/editing bottles **without** wiping the volume, use `./scripts/add-bottle.sh` — see [Getting Started With Your Own Bottles](#getting-started-with-your-own-bottles).

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

This repo comes with ~44 default bottles. Two flows depending on what you're doing.

### Flow A — Add one bottle to a running stack (recommended)

Bring the stack up with backend and frontend ports published on localhost (the script defaults to `http://127.0.0.1:8080` for the backend and `http://127.0.0.1:3000` for the frontend; override with `BACKEND_HOST=` / `FRONTEND_HOST=` if you publish elsewhere):

```bash
docker compose -f compose.yaml -f compose.build.yaml up -d
```

Then run the orchestrator:

```bash
# Write a single bottle definition to a JSON file (see schema below),
# then run:
./scripts/add-bottle.sh /tmp/new_bottle.json
```

What it does, in order:

1. Validates JSON shape (16 flavor dimensions, required keys).
2. Appends to `scripts/data/bottles_seed.json` — idempotent by `(brand, label)`, so re-running is safe.
3. `POST /api/bottles/_bulk` — upserts the full seed into the live database. **No `docker compose down -v`** needed.
4. `GET /inventory/flavor-map/regenerate` — frontend re-runs UMAP + DBSCAN against the new state.
5. `docker exec mix-ml-frontend python -m app._tools.calibrate --write` — refreshes `frontend/app/data/cluster_impressions.json` inside the container (the file is bind-mounted, so the change lands on the host immediately). Curated impressions whose bottle set overlaps the new cluster by ≥75% are preserved; new clusters get a `<Primary>-leaning · TODO:` placeholder.
6. Prints the clusters and outliers that still need a curated impression.
7. Prints a suggested `git add … && git commit …`. **Never auto-commits.**

After the script finishes:

```bash
# Hand-write impressions for any TODO clusters the script flagged
$EDITOR frontend/app/data/cluster_impressions.json

# Frontend picks up the new text on the next request (file is bind-mounted
# and read with an mtime-aware cache). Restart only needed if you also want
# to clear the cached 2D map: docker compose restart frontend.

# Then commit the bottle + curated impressions
git add scripts/data/bottles_seed.json frontend/app/data/cluster_impressions.json
git commit -m "feat(bottles): add <name>"
git push
```

**Optional flag:** `./scripts/add-bottle.sh --regen-seed new_bottle.json` also rewrites `scripts/seed.sql` and `db/seed.sql` so a future `docker compose down -v && up -d` reseed includes the new bottle without API replay.

**Re-cluster without adding a bottle:** if you tweaked a flavor profile in place, run `./scripts/regen-flavor-map.sh` — same regen + calibrate + TODO surface, no DB write.

### Flow B — Cold start with a custom inventory (first deploy)

Use this when you want a fresh DB seeded entirely from `bottles_seed.json` instead of replaying the API.

1. Edit `scripts/data/bottles_seed.json`. One entry per bottle:

   ```json
   {
     "class_name": "Single Malt Scotch (peated)",
     "brand": "Talisker",
     "label": "10 Year Old",
     "abv": 45.8,
     "on_hand": true,
     "flavor_profile": {
       "sweet": 1, "bitter": 3, "sour": 0, "citrusy": 1,
       "fruity": 2, "herbal": 1, "floral": 0, "spicy": 2,
       "smoky": 4, "vanilla": 1, "woody": 2, "minty": 1,
       "earthy": 1, "umami": 0, "body": 4, "intensity": 4
     },
     "notes": null
   }
   ```

   `class_name` must exist in the ingredient hierarchy in `scripts/generate_seed_sql.py` (or be added to it). Each `flavor_profile` value is 0–5 (0 = not present, 5 = dominant).

2. Regenerate the seed:

   ```bash
   cd scripts && python generate_seed_sql.py data/iba_cocktails_normalized.json
   cp seed.sql ../db/seed.sql
   ```

   The script reads `bottles_seed.json` automatically.

3. Reseed Postgres and bring the stack up:

   ```bash
   docker compose down -v && docker compose up -d
   ```

4. Calibrate impressions against the fresh collection:

   ```bash
   ./scripts/regen-flavor-map.sh
   ```

   Edit any `TODO`-flagged impressions, then commit `bottles_seed.json`, `db/seed.sql`, `scripts/seed.sql`, and `frontend/app/data/cluster_impressions.json`.

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
- UMAP parameters: `n_neighbors=10`, `min_dist=0.3`, `metric=euclidean`, `random_state=42` (deterministic given stable bottle order)
- DBSCAN parameters: `eps=0.6`, `min_samples=2` (tunable, see calibration)
- Bottle order from `/api/bottles` is fully deterministic (`ORDER BY ic.name, b.brand, b.label NULLS FIRST, b.id`); without this UMAP gave different clusters for `limit=100` vs `limit=200` callers
- Plotly.js for rendering (client-side pan/zoom/click)
- Cluster impressions stored in `frontend/app/data/cluster_impressions.json` — **bind-mounted into the frontend container**, so edits don't require an image rebuild (an mtime-aware cache picks up changes between requests)
- Auto-generated impressions follow the format `<Primary>-leaning · Signature notes: …` so the panel always extracts a real title (never falls back to "Outlier" for a real cluster)

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
| GET | `/api/bottles` | Your bottle inventory (paginated `{total, items}`) |
| POST | `/api/bottles` | Create one bottle |
| POST | `/api/bottles/_bulk` | Idempotent upsert by `(brand, label)` — used by `scripts/add-bottle.sh` |
| PATCH | `/api/bottles/{id}` | Update bottle (flavor profile, on-hand, etc.) |
| DELETE | `/api/bottles/{id}` | Remove a bottle |
| GET | `/api/recipes` | IBA recipes with `?category=` filter |
| GET | `/api/cocktails/can-make-now` | Feasible recipe IDs + names |
| GET | `/api/flavor/distance?bottle_a=X&bottle_b=Y` | Flavor distance breakdown |
| GET | `/api/flavor/similar-bottles?bottle_id=X` | Ranked neighbors |
| GET | `/api/cocktails/{id}/substitutions` | Per-recipe alternatives |
| GET | `/api/bottles/optimize-shopping?budget=K` | ILP K-bottle purchase plan |

Frontend also exposes one dev/operational hook:

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/inventory/flavor-map/regenerate` | Re-runs UMAP + DBSCAN on the live frontend without restart — used by `scripts/add-bottle.sh` |

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
- **Clustering**: `umap-learn` (2D projection) + `scikit-learn` DBSCAN + SciPy hierarchical clustering (heatmap)

Setup: `frontend/README.md`

### Database (`db/`)

PostgreSQL 16 schema (singular table names; see `scripts/generate_seed_sql.py:260` for full DDL):
- `recipe` — 102 IBA cocktails
- `recipe_ingredient` — many-to-many with amount, unit, optional/garnish flags, alternative groups
- `bottle` — your personal inventory; 16-dimensional flavor profile stored as `JSONB` on the same row
- `ingredient_class` — taxonomy with parent_id hierarchy (spirits, bitters, juices, garnishes); `is_garnish` and `is_commodity` flags mark always-available pantry items

Database schema and seed are generated by `scripts/generate_seed_sql.py`.

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

Impressions are calibrated to a specific bottle set via a 75% overlap matching heuristic — when a new cluster's bottle set overlaps an existing impression's bottle set by ≥75%, the curated text is preserved; otherwise an auto-generated `<Primary>-leaning · TODO:` placeholder is written. The 2D-map's UMAP + DBSCAN result is deterministic given identical bottle order, so calibration output matches the live frontend exactly when run inside the frontend container (see "Why inside the container?" below).

**Default workflow (single bottle, live stack):**

```bash
./scripts/add-bottle.sh /tmp/new_bottle.json
```

See [Flow A](#flow-a--add-one-bottle-to-a-running-stack-recommended). The script handles upsert + regenerate + calibrate + TODO surface end to end.

**Re-cluster only (no DB write):**

```bash
./scripts/regen-flavor-map.sh
```

Use after editing a flavor profile in place or removing a bottle via the API.

**Tuning DBSCAN:**

If clustering looks wrong, run calibrate manually with different params:

```bash
docker exec --user 0 mix-ml-frontend \
    python -m app._tools.calibrate \
        --backend-url http://backend:8080 \
        --eps 0.7 --min-samples 2 --write
```

- Larger `eps` → fewer, larger clusters
- Smaller `eps` → more, tighter clusters
- Typical range for 30–80 bottles: 0.4–0.8
- Typical UMAP coordinate range: x ≈ 5 units, y ≈ 6 units
- `min_samples` must be ≥2; raising it pushes more bottles into the outlier ring

**Why inside the container?** `scikit-learn` minor versions can change DBSCAN cluster IDs even with identical input. The image pins `scikit-learn 1.8.0` and `umap-learn 0.5.12`; a host venv can drift to newer versions and silently produce a different partition than what the frontend renders. Calibrating inside the container guarantees the impressions file matches the live clusters.

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
# Live-stack path (preferred — no DB wipe, no image rebuild):
./scripts/add-bottle.sh /tmp/new_bottle.json --regen-seed
# Hand-curate any TODO impressions, then:
git add scripts/data/bottles_seed.json frontend/app/data/cluster_impressions.json \
        scripts/seed.sql db/seed.sql
git commit -m "feat(bottles): add <name>"
git push

# Cold-start path (only if the cluster is being reseeded from scratch):
cd scripts && python generate_seed_sql.py data/iba_cocktails_normalized.json
cp seed.sql ../db/seed.sql
# Commit, push, ArgoCD will pick up the new db/seed.sql on the next PostSync.
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
│   │   ├── _tools/
│   │   │   └── calibrate.py           # In-container 2D-map calibrator
│   │   └── data/
│   │       └── cluster_impressions.json # Human-written cluster descriptions (bind-mounted)
│   ├── tests/                         # 80 unit/integration tests
│   └── pyproject.toml
├── db/                                # Database schema
│   └── seed.sql                       # IBA recipes + default bottles
├── scripts/                           # Offline tools
│   ├── add-bottle.sh                  # One-command add-a-bottle pipeline (primary)
│   ├── regen-flavor-map.sh            # Re-cluster only (no bottle write)
│   ├── generate_seed_sql.py           # Build seed.sql from bottles_seed.json + IBA JSON
│   ├── calibrate_clusters.py          # Host-side calibrator (used when no stack is running)
│   ├── scrape_iba.py                  # Download IBA recipes
│   ├── analyze_iba.py                 # Generate reports
│   ├── data/
│   │   ├── bottles_seed.json          # Your bottle inventory (source of truth)
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
├── compose.yaml                       # Production image versions + bind mounts
├── compose.build.yaml                 # Local dev overrides (exposes ports, builds from source)
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
A: Write a single-bottle JSON file and run `./scripts/add-bottle.sh /tmp/new_bottle.json`. The script upserts into the live DB via `/api/bottles/_bulk` (no `down -v`), triggers a frontend regenerate, refreshes `cluster_impressions.json` inside the container, and surfaces any clusters that need a curated impression. See [Flow A](#flow-a--add-one-bottle-to-a-running-stack-recommended).

**Q: What if my cluster impressions are stale after adding bottles?**
A: `add-bottle.sh` already runs the in-container calibrator at the end of every invocation. For a re-cluster without a DB change (e.g. you tweaked a flavor profile), run `./scripts/regen-flavor-map.sh`. Both use the 75% overlap heuristic to preserve curated impressions and flag the rest with `<Primary>-leaning · TODO:` placeholders.

**Q: Do I need to rebuild the frontend image after editing a cluster impression?**
A: No. `cluster_impressions.json` is bind-mounted from the host into the container, and the loader is mtime-aware. Edit the file, request a page, the new text is served. `docker compose restart frontend` is only needed if you also want to clear the cached 2D map itself.

## License & Attribution

IBA cocktail data sourced from [iba-world.com](https://iba-world.com).

Flavor profiles, bottle additions, and optimizations are author's own.

---

**Last updated:** June 2026
**Latest versions:** frontend v1.3.13 · backend v1.3.2
