# Mix/ML — Cocktail Intelligence Platform

A data-driven cocktail platform built on the 102 official IBA recipes.
Scrapes, normalizes, stores, and serves cocktail data through a REST API,
a flavor-distance engine, a substitution recommender, and a web UI.

## Architecture

```
┌─────────────┐      ┌──────────────┐      ┌──────────────┐
│  Frontend   │─────▶│   Backend    │─────▶│ PostgreSQL   │
│  port 3000  │ HTTP │   port 8080  │  SQL │     16       │
│  HTMX+Jinja │      │   FastAPI    │      │  (CRC/OCP)   │
└─────────────┘      └──────────────┘      └──────────────┘
```

| Component | Path | Description |
|-----------|------|-------------|
| Backend API | `backend/` | FastAPI REST API — recipes, bottles, feasibility, flavor distance, substitutions, shopping optimizer |
| Frontend | `frontend/` | FastAPI + Jinja2 + HTMX web UI — cocktail browser, inventory, flavor map, substitution explorer |
| Manifests | `manifests/` | Kustomize manifests + ArgoCD Application for OpenShift Local (CRC) |
| Scripts | `scripts/` | Pipeline tools (scraper, analyzer, seed generator), GitOps bootstrap |
| Database | `db/` | Canonical `seed.sql` for deployment |

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 16 (via CRC port-forward or local)
- `oc` CLI (for CRC deployments)

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Port-forward to CRC DB (from WSL2, use Windows oc.exe)
/mnt/c/Users/<user>/.crc/bin/oc/oc.exe port-forward svc/postgres 5432:5432 \
  -n mix-ml --address 0.0.0.0 &

export DATABASE_URL="postgresql+psycopg://cocktailuser:<password>@localhost:5432/cocktails"
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

### Frontend

```bash
cd frontend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

BACKEND_URL="http://localhost:8080" uvicorn app.main:app \
  --host 0.0.0.0 --port 3000 --reload
```

Open http://localhost:3000.

### Tests

```bash
# Backend (requires live DB)
cd backend && pytest tests/ -v    # 104 tests

# Frontend (no live backend needed)
cd frontend && pytest tests/ -v   # 80 tests
```

## Deployment & GitOps

The system runs on OpenShift Local (CRC), managed via ArgoCD (Red Hat OpenShift GitOps).
ArgoCD watches `manifests/overlays/crc/` on `main` branch. All cluster changes go through Git.

### Prerequisites

- OpenShift Local (CRC) running, ~16 GB RAM allocated
- `oc` CLI logged in as `kubeadmin` (cluster-admin)
- `git` and `bash`

### One-Time Bootstrap

1. **Set required environment variables:**
   ```bash
   export POSTGRES_PASSWORD=$(openssl rand -base64 24)
   export POSTGRES_ADMIN_PASSWORD=$(openssl rand -base64 24)
   # Optional: for private ghcr.io images
   export GITHUB_USERNAME=unusualfor
   export GITHUB_TOKEN=ghp_...
   ```

2. **Set up secrets in cluster:**
   ```bash
   bash scripts/setup-secrets.sh
   ```

3. **Install operators + create ArgoCD Application:**
   ```bash
   bash scripts/bootstrap-gitops.sh
   ```

4. **Open ArgoCD UI** (URL printed by the script). Username: `admin`, password from script output.

5. **Find the `mix-ml` Application. Click "Sync" to deploy.**
   ArgoCD renders Kustomize, compares desired state with cluster, and applies diffs.

6. **Once pods are healthy, seed the database:**
   ```bash
   oc apply -f manifests/base/seed-job.yaml -n mix-ml
   oc wait --for=condition=complete job/postgres-seed -n mix-ml --timeout=180s
   ```

### Daily Operations

#### Updating Manifests

1. Edit files under `manifests/base/` or `manifests/overlays/crc/`.
2. Commit and push to `main`.
3. In ArgoCD UI, click "Refresh" then "Sync" on the `mix-ml` Application.
4. Verify resources are healthy.

#### Updating Application Code

Code in `backend/` and `frontend/` is built into images on `ghcr.io`.
For now this is manual (Slice 2 will introduce Tekton automation):

1. Build image: `podman build -t ghcr.io/unusualfor/mix-ml-backend:vX.Y.Z backend/`
2. Push: `podman push ghcr.io/unusualfor/mix-ml-backend:vX.Y.Z`
3. Edit `manifests/base/backend-deployment.yaml` to use new tag.
4. Commit, push, sync via ArgoCD.

#### Database Seeding (Manual Operation)

The database is seeded from `db/seed.sql`, generated from the source data.
This is intentionally manual — data changes are infrequent and high-impact.

**When to re-seed:** adding bottles, updating IBA recipes, schema changes.

**How to re-seed:**

```bash
# 1. Regenerate seed.sql
cd scripts && python generate_seed_sql.py data/iba_cocktails_normalized.json

# 2. Wipe existing tables
oc exec deploy/postgres -n mix-ml -- psql -U cocktailuser -d cocktails -c "
  DROP TABLE IF EXISTS recipe_ingredient CASCADE;
  DROP TABLE IF EXISTS bottle CASCADE;
  DROP TABLE IF EXISTS recipe CASCADE;
  DROP TABLE IF EXISTS ingredient_class CASCADE;"

# 3. Re-trigger the seed job
oc delete job postgres-seed -n mix-ml --ignore-not-found
oc apply -f manifests/base/seed-job.yaml -n mix-ml

# 4. Verify counts
oc exec deploy/postgres -n mix-ml -- psql -U cocktailuser -d cocktails -c "
  SELECT 'classes', COUNT(*) FROM ingredient_class
  UNION ALL SELECT 'recipes', COUNT(*) FROM recipe
  UNION ALL SELECT 'ingredients', COUNT(*) FROM recipe_ingredient
  UNION ALL SELECT 'bottles', COUNT(*) FROM bottle;"
```

### GitOps Validation

```bash
bash tests/test_gitops_setup.sh
```

### Troubleshooting

**Pod CrashLoopBackOff with "POSTGRES_USER not set"**
— Secret `postgres-credentials` missing. Re-run `bash scripts/setup-secrets.sh`.

**ArgoCD shows "OutOfSync" but you didn't change anything**
— Cluster drift from manual `oc apply`. Click "Sync" in ArgoCD to reconcile.

**ImagePullBackOff for backend/frontend**
— ghcr.io credentials missing. Re-run `setup-secrets.sh` with `GITHUB_USERNAME` and `GITHUB_TOKEN`.

### Future Enhancements (Out of Scope)

- **Sealed Secrets / External Secrets Operator**: secrets currently use placeholder + setup script. Production would use sealed secrets committed to Git, or External Secrets fetching from a vault.
- **Multi-environment** (dev/staging/prod): current setup is single CRC environment. Production uses overlays per environment + promotion workflows.
- **Image scanning** (Trivy, ACS): pipeline images go to ghcr.io without security analysis.
- **Policy-as-code** (Kyverno, OPA Gatekeeper): no admission controller policies enforced.
- **Webhook-triggered pipelines**: CRC is not internet-exposed. Tekton triggers run via manual `tkn pipeline start` (Slice 2).
- **Sync waves and hooks**: ArgoCD Application could declare ordering. Current config is flat single-wave sync.
- **Auto-sync**: currently manual sync only. Production could enable auto-sync with auto-prune.

## Scraper

```bash
cd scripts
python scrape_iba.py
```

1. Downloads the IBA recipe index from [iba-world.com](https://iba-world.com)
2. Visits each recipe page (2s delay between requests)
3. Extracts name, category, ingredients, method, garnish
4. Saves to `iba_cocktails.json` (alphabetically sorted)

Idempotent — skips recipes already present if the output file exists.

### IBA Categories

| JSON key | Site name |
|----------|-----------|
| `unforgettable` | The Unforgettables |
| `contemporary` | Contemporary Classics |
| `new_era` | New Era |

### Ingredient Parsing

| Text pattern | `amount` | `unit` | `name` |
|--------------|----------|--------|--------|
| `30 ml Gin` | `30` | `"ml"` | `"Gin"` |
| `2 dashes Angostura` | `2` | `"dash"` | `"Angostura"` |
| `Few Dashes Bitters` | `null` | `"dash"` | `"Bitters"` |
| `1 bar spoon Sugar` | `1` | `"bsp"` | `"Sugar"` |
| `Champagne to top` | `null` | `"top"` | `"Champagne"` |
| `Soda Water` (bare) | `null` | `null` | `"Soda Water"` |

## Analyzer

```bash
cd scripts
python analyze_iba.py data/iba_cocktails.json
```

No dependencies beyond the standard library.

| Output file | Content |
|-------------|---------|
| `report_ingredient_frequency.csv` | Ingredient frequency with recipe lists |
| `report_unit_inventory.csv` | Units of measure, frequency, examples |
| `report_amount_anomalies.txt` | Null/zero/non-numeric amounts |
| `report_ingredient_clusters.txt` | Similar-name clusters (merge candidates) |
| `report_summary.md` | Overview: categories, top-20 ingredients, glassware, techniques |
