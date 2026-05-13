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

### Option A — OpenShift GitOps (official)

The canonical deployment runs on **OpenShift Local (CRC)** with ArgoCD managing the full lifecycle. DB seeding happens automatically via a PostSync hook on every sync.

**Prerequisites:** OpenShift Local (CRC) running (~16 GB RAM), `oc` CLI logged in as `kubeadmin`, a GitHub PAT with `repo` + `write:packages` scope.

```bash
# 1. Set secrets
export POSTGRES_PASSWORD=$(openssl rand -base64 24)
export POSTGRES_ADMIN_PASSWORD=$(openssl rand -base64 24)
export GITHUB_USERNAME=unusualfor
export GITHUB_TOKEN=ghp_...
bash scripts/setup-secrets.sh

# 2. Bootstrap ArgoCD + Application
bash scripts/bootstrap-gitops.sh

# 3. Open ArgoCD UI (URL from script output), click Sync on mix-ml

# 4. Bootstrap CI pipelines (optional, for image builds)
bash scripts/bootstrap-ci.sh
bash scripts/setup-ci-secrets.sh
```

After sync, the PostSync hook seeds Postgres automatically with 102 IBA recipes and 42 bottles. App is live at the OpenShift Route printed by `oc get route -n mix-ml`.

### Option B — Podman / Docker Compose (lightweight)

Run everything locally with a single command. No Kubernetes required.

```bash
podman compose up -d      # or: docker compose up -d
```

This starts Postgres 16, backend (FastAPI), and frontend (HTMX) as containers. Postgres is seeded automatically from `db/seed.sql` on first boot.

| Service  | URL                    |
|----------|------------------------|
| Frontend | http://localhost:3000   |
| Backend  | http://localhost:8080   |
| Postgres | localhost:5432          |

To rebuild after code changes:

```bash
podman compose up -d --build
```

To tear down (data persists in volume):

```bash
podman compose down           # keep data
podman compose down -v        # wipe data + re-seed on next up
```

### Option C — Bare-metal (development)

For hacking on individual components without containers.

**Prerequisites:** Python 3.11+, a running PostgreSQL 16 instance seeded with `db/seed.sql`.

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
export DATABASE_URL="postgresql+psycopg://cocktailuser:cocktail@localhost:5432/cocktails"
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload

# Frontend (separate terminal)
cd frontend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
BACKEND_URL="http://localhost:8080" uvicorn app.main:app --host 0.0.0.0 --port 3000 --reload
```

### Tests

```bash
cd backend  && pytest tests/ -v    # 104 tests (requires live DB)
cd frontend && pytest tests/ -v    # 80 tests  (no live backend needed)
```

## Deployment & GitOps (detailed)

> **Quick version**: see [Option A](#option-a--openshift-gitops-official) above. This section covers the architecture and daily workflows in depth.

### Architecture

The mix-ml deployment pipeline implements a complete GitOps workflow on OpenShift Local (CRC):

```mermaid
flowchart LR
    Dev[Developer<br/>local laptop] -->|git push code| GH[GitHub repo]
    Dev -->|tkn pipeline start| TK[Tekton Pipelines<br/>mix-ml-ci namespace]

    TK -->|clone source| GH
    TK -->|lint + test| TK
    TK -->|build + push| GHCR[ghcr.io<br/>container registry]
    TK -->|commit manifest update| GH

    GH -->|polled every 3min| Argo[ArgoCD<br/>openshift-gitops namespace]
    Argo -->|manual sync via UI| Workloads[Workloads<br/>mix-ml namespace]

    GHCR -.->|pulled by pods| Workloads

    Workloads --> Postgres[(Postgres)]
    Workloads --> Backend[Backend FastAPI]
    Workloads --> Frontend[Frontend HTMX/FastAPI]

    Frontend -->|HTTP cluster-internal| Backend
    Backend -->|SQL| Postgres

    User[End user] -->|HTTPS via Route| Frontend

    classDef external fill:#fef3c7,stroke:#92400e
    classDef cluster fill:#dbeafe,stroke:#1e40af
    classDef workload fill:#d1fae5,stroke:#065f46

    class Dev,GH,GHCR,User external
    class TK,Argo cluster
    class Workloads,Postgres,Backend,Frontend workload
```

The architecture separates three concerns:

- **External** (yellow): developer environment, source code repository, container registry, end users
- **Cluster automation** (blue): Tekton pipelines build images; ArgoCD synchronizes desired state from Git to running cluster
- **Workloads** (green): the actual application components (Postgres, backend, frontend)

Key design decisions:

- **Manifest-driven deployment**: the cluster state is fully determined by `manifests/` in the repo. No `oc apply` outside of bootstrap.
- **Immutable image tags**: every build produces `git-<sha>` tag. Manifests reference SHA tags, never `latest`. Rollback is a tag change committed to Git.
- **Manual sync gate**: ArgoCD does not auto-sync. A human reviews the diff in the ArgoCD UI before applying changes.
- **Single-direction Git flow**: developers commit application code; Tekton commits manifest bumps; ArgoCD reads only. No circular updates.

The system runs on OpenShift Local (CRC), managed via ArgoCD (Red Hat OpenShift GitOps).
ArgoCD watches `manifests/overlays/crc/` on `main` branch. All cluster changes go through Git.

### Prerequisites & Bootstrap

See [Option A — OpenShift GitOps](#option-a--openshift-gitops-official) in Quick Start.

### Daily Workflow

#### Scenario: small backend change
1. Edit code in `backend/`, commit and push
2. `bash scripts/build-backend.sh`
3. Wait for pipeline (~5-10 min)
4. ArgoCD UI: Refresh → Sync
5. Verify: `oc get pods -n mix-ml -l app.kubernetes.io/name=backend`

#### Scenario: small frontend change
Same as above but `bash scripts/build-frontend.sh`.

#### Scenario: coordinated release (backend + frontend together)
1. Make changes in both `backend/` and `frontend/`, commit and push
2. `bash scripts/build-all.sh`
3. Wait for both pipelines
4. ArgoCD UI: Refresh → Sync (single sync applies both manifest updates)
5. Verify both pods restarted

#### Scenario: manifest-only change (e.g. scale replicas, change env var)
1. Edit `manifests/base/...yaml`, commit and push
2. No pipeline trigger needed
3. ArgoCD UI: Refresh → Sync

#### Scenario: rollback
1. Revert the kustomization.yaml change to a previous SHA tag:
   ```bash
   git revert <bump-commit-sha>
   git push
   ```
2. ArgoCD UI: Refresh → Sync
3. Pods restart with previous image

#### Updating Manifests

1. Edit files under `manifests/base/` or `manifests/overlays/crc/`.
2. Commit and push to `main`.
3. In ArgoCD UI, click "Refresh" then "Sync" on the `mix-ml` Application.
4. Verify resources are healthy.

#### Database Seeding

Seeding is **automatic** — an ArgoCD PostSync hook runs `db/seed.sql` on every sync. The SQL is idempotent (drops and recreates all tables).

**To update seed data** (e.g. add bottles, fix recipes):

```bash
# 1. Edit scripts/data/bottles_seed.json or iba_cocktails_normalized.json
# 2. Regenerate seed.sql
cd scripts && python generate_seed_sql.py data/iba_cocktails_normalized.json

# 3. Copy to all locations
cp seed.sql ../manifests/base/seed.sql && cp seed.sql ../db/seed.sql

# 4. Commit, push, sync in ArgoCD — PostSync hook re-seeds automatically
```

## CI/CD: Application Pipelines

Both the backend and frontend are built by Tekton pipelines running in the `mix-ml-ci` namespace. The pipelines share a common set of reusable Tasks, parameterized by `app-path`.

### Pipeline flow

Each pipeline (`backend-ci` and `frontend-ci`) follows the same DAG:

```
git-clone → compute-image-tag ─┐
         → lint-and-test ──────┼→ build-and-push → update-manifest
                               │     (buildah)       (yq + git push)
```

1. Clones the repository at the specified branch/commit
2. Lints (ruff) and tests (pytest) the Python code
3. Builds the container image with Buildah
4. Pushes to `ghcr.io` with two tags: `git-<short-sha>` (immutable) and `latest` (mobile)
5. Updates `manifests/base/kustomization.yaml` with a Kustomize `images:` override referencing the new immutable tag
6. Commits and pushes the manifest change to `main`

ArgoCD detects the manifest change at the next refresh and shows `OutOfSync`. Sync is manual.

### Triggering builds

```bash
# Backend only
bash scripts/build-backend.sh

# Frontend only
bash scripts/build-frontend.sh

# Both in parallel
bash scripts/build-all.sh
```

Scripts read the current git branch via `git branch --show-current`. Commit and push any local changes before triggering. `--showlog` streams pipeline output live.

### Watching the pipeline

- OpenShift console → **Pipelines** → namespace `mix-ml-ci`
- Or via CLI:
  ```bash
  tkn pipelinerun list -n mix-ml-ci
  tkn pipelinerun logs <name> -f -n mix-ml-ci
  ```

### Validating the CI setup

```bash
bash tests/test_backend_ci.sh      # backend pipeline checks
bash tests/test_frontend_ci.sh     # frontend pipeline checks
bash tests/test_full_gitops.sh     # full stack validation
```

### Common failure modes

| Failure | Cause | Fix |
|---------|-------|-----|
| `lint-and-test` fails | Code has lint errors or test failures | Fix locally, commit, re-run |
| `build-and-push` auth error | `ghcr-credentials` expired or missing | Re-run `setup-ci-secrets.sh` |
| `update-manifest` git push error | `github-credentials` expired or PAT lacks `repo` scope | Re-run `setup-ci-secrets.sh` with new PAT |
| ArgoCD doesn't show OutOfSync | Polling interval ~3 min | Click **Refresh** in UI |
| Frontend lint-and-test numpy/scipy error | Heavy deps timeout in install step | Retry; CRC may need more resources |

### Troubleshooting

**Pod CrashLoopBackOff with "POSTGRES_USER not set"**
— Secret `postgres-credentials` missing. Re-run `bash scripts/setup-secrets.sh`.

**ArgoCD shows "OutOfSync" but you didn't change anything**
— Cluster drift from manual `oc apply`. Click "Sync" in ArgoCD to reconcile.

**ImagePullBackOff for backend/frontend**
— ghcr.io credentials missing. Re-run `setup-secrets.sh` with `GITHUB_USERNAME` and `GITHUB_TOKEN`.

### Why manual sync and not auto-sync?

This iteration uses manual ArgoCD sync deliberately: it keeps a human in the loop between "image built" and "image deployed", which is useful for portfolio-grade demos and for catching mistakes. Production setups often enable auto-sync with retries — straightforward change to `Application` spec, deferred to a future iteration.

### Future enhancements (out of scope for this iteration)

This iteration delivers a complete but minimal GitOps workflow. The following enhancements are deliberately not implemented, documented for transparency and as a roadmap:

**Security & secrets**
- Sealed Secrets or External Secrets Operator (current: placeholder + setup script)
- Image scanning (Trivy, Sysdig, Red Hat ACS)
- SBOM generation in pipeline
- Pod Security Standards enforcement
- NetworkPolicy isolation between namespaces

**Deployment patterns**
- Multi-environment (dev/staging/prod) via overlay promotion
- Auto-sync with retry policies and self-heal
- Blue-green or canary deployments via Argo Rollouts
- Multi-cluster GitOps with ApplicationSet

**CI/CD**
- Webhook-triggered pipelines (requires cluster ingress, not available on CRC)
- Multi-arch image builds (arm64 + amd64)
- Pull-request-based workflow with required reviews
- Slack/email notifications on pipeline status
- Cached layer builds for faster iteration

**Observability**
- Prometheus + Grafana dashboards for application metrics
- Loki for centralized logging
- Distributed tracing (OpenTelemetry)
- Alert routing (AlertManager → PagerDuty/Slack)

**Governance**
- Policy-as-code (Kyverno, OPA Gatekeeper)
- Cost monitoring (Kubecost)
- Compliance scanning (Red Hat ACM)

These are intentionally deferred to keep the current iteration focused on the GitOps fundamentals demonstrable on a single CRC node.

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
