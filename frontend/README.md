# mix-ml Frontend

Web UI for the mix-ml cocktail feasibility engine.  
Separate HTTP service that calls the backend API and renders HTML via Jinja2 + HTMX.

## Stack

- **Python 3.11+** / FastAPI / Jinja2
- **HTMX 1.9** for client-side interactivity (CDN, no build step)
- **Tailwind CSS** via CDN (dev); precompiled `static/css/app.css` in prod
- **httpx** for backend HTTP calls
- No Node, no bundler, no npm

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
python -m pytest tests/ -v
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

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Home page — cocktails you can make now |
| GET | `/cocktails/can-make-now?category=<filter>` | Partial list (HTMX) or full page |
| GET | `/healthz` | Health check (always 200) |
| GET | `/readyz` | Readiness (pings backend `/healthz`) |
