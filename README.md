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
| Manifests | `manifests/` | Kustomize manifests for OpenShift Local (CRC) |
| Scripts | `scripts/` | Offline analysis tools (flavor matrix heatmap, clustering) |
| Scraper | `scrape_iba.py` | IBA recipe scraper → `iba_cocktails.json` |
| Analyzer | `analyze_iba.py` | Descriptive reports (frequency, clusters, anomalies) |
| Seed generator | `generate_seed_sql.py` | Builds `seed.sql` from JSON + taxonomy CSV |

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
  -n cocktail-db --address 0.0.0.0 &

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

## Scraper

```bash
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
python analyze_iba.py iba_cocktails.json
```

No dependencies beyond the standard library.

| Output file | Content |
|-------------|---------|
| `report_ingredient_frequency.csv` | Ingredient frequency with recipe lists |
| `report_unit_inventory.csv` | Units of measure, frequency, examples |
| `report_amount_anomalies.txt` | Null/zero/non-numeric amounts |
| `report_ingredient_clusters.txt` | Similar-name clusters (merge candidates) |
| `report_summary.md` | Overview: categories, top-20 ingredients, glassware, techniques |
