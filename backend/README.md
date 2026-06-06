# Backend API

FastAPI REST API for the mix-ml cocktail intelligence platform.

**For overview, quick start, and getting your own bottles working, see the [root README](../README.md).**

## Stack

- **Python 3.11+** / FastAPI / SQLAlchemy
- **psycopg3** — PostgreSQL 16 driver
- **OR-Tools CP-SAT** — integer linear programming solver (shopping optimizer)
- **pandas** — data manipulation

## Local Development

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Using Docker Postgres (recommended)
docker run -d --name mix-ml-db \
  -e POSTGRES_DB=cocktails \
  -e POSTGRES_USER=cocktailuser \
  -e POSTGRES_PASSWORD=cocktail \
  -p 5432:5432 \
  postgres:16-alpine

# Wait for DB, then:
export DATABASE_URL="postgresql+psycopg://cocktailuser:cocktail@localhost:5432/cocktails"
psql -h localhost -U cocktailuser -d cocktails < ../db/seed.sql

# Run server
uvicorn app.main:app --reload
```

API available at **http://localhost:8000/docs** (interactive Swagger UI).

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/healthz` | Liveness probe (always 200) |
| GET | `/readyz` | Readiness probe (checks DB connection) |
| GET | `/api/bottles` | Your bottle inventory as `{total, items}` (paginated, `?limit=` up to 500) |
| GET | `/api/bottles/{id}` | Bottle detail |
| POST | `/api/bottles` | Create bottle |
| POST | `/api/bottles/_bulk` | Idempotent upsert by `(brand, label)` — primary entry point for `scripts/add-bottle.sh` |
| PATCH | `/api/bottles/{id}` | Update bottle (flavor profile, on-hand flag, etc.) |
| DELETE | `/api/bottles/{id}` | Delete bottle |
| GET | `/api/recipes` | IBA recipes (filterable: `?category=`, `?search=`, `?limit=`, `?offset=`) |
| GET | `/api/recipes/{id}` | Recipe detail with ingredients |
| GET | `/api/recipes/by-name?name=Margarita` | Recipe lookup by name |
| GET | `/api/cocktails/can-make-now` | Feasible recipes with your bottles |
| GET | `/api/cocktails/{id}/feasibility` | Per-recipe ingredient satisfaction |
| GET | `/api/flavor/distance?bottle_a=X&bottle_b=Y` | Flavor distance (0 to 1) + breakdown |
| GET | `/api/flavor/similar-bottles?bottle_id=X&top=10` | Ranked neighbors by flavor distance |
| GET | `/api/cocktails/{id}/substitutions` | Per-recipe ingredient alternatives (`?tier=strict\|loose\|both`) |
| GET | `/api/bottles/optimize-shopping?budget=K` | ILP K-bottle shopping plan (`?explain=true` for details) |

## Tests

```bash
pytest tests/ -v   # 104 tests, requires live Postgres
```

Tests create a temporary `test_cocktail` schema, insert minimal data, drop after session.

## Flavor Distance Metric

Computes weighted Euclidean distance between two 16-dimensional flavor profiles:

$$d = w_g \cdot d_{\text{gustative}} + w_s \cdot d_{\text{structural}}$$

**Dimensions:**
- **Gustative** (14): sweet, bitter, sour, citrusy, fruity, herbal, floral, spicy, smoky, vanilla, woody, minty, earthy, umami
- **Structural** (2): body, intensity

Each value is 0–5. Each sub-distance normalized to [0, 1].

**Default weights:** $w_g = 0.7$, $w_s = 0.3$ (can be overridden per request).

## Substitutions

Two tiers based on flavor distance from the required ingredient:

| Tier | Threshold | Criteria |
|------|-----------|----------|
| `strict` | ≤ 0.25 | Same family + close flavor match |
| `loose` | ≤ 0.20 | Any bottle + reasonable match |

Excludes anti-duplicates (classes already used in recipe) and already-owned satisfying bottles.

## Shopping Optimizer (ILP)

Given a budget of K bottles (1–15), finds the optimal purchase set that maximizes newly-feasible IBA recipes.

**Model:**
- Variables: `x_c` (buy class c?), `y_r` (recipe r becomes feasible?)
- Constraints: `sum(x) ≤ budget`; for each unsatisfied requirement in r, `y_r ≤ sum(x_c)` where c can satisfy it
- Objective: `max sum(weight[category] × y_r)`

**Categories:** Unforgettables (3x weight), Contemporary Classics (2x), New Era (1x) — tunable.

**Params:** `budget`, `explain`, `solver_timeout_seconds`.

## Ingredient Classes & Commodity Flag

The `is_commodity` flag on `ingredient_class` marks ingredients assumed always available (citrus, sugar, soda, generic spirits like Champagne) without requiring explicit bottle inventory entries.

To track Champagne as an actual inventoried bottle, either:
1. Re-flag the class as non-commodity via SQL, or
2. Create a new finer-grained class (e.g., "Brut Champagne")

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+psycopg://...` | SQLAlchemy connection string |
| `LOG_LEVEL` | `INFO` | Python logging level |

## Database Schema

Tables created by `db/seed.sql` (singular names — see `scripts/generate_seed_sql.py:260` for DDL):

- `ingredient_class` — taxonomy with `(parent_id, name, is_garnish, is_commodity)`
- `bottle` — personal inventory; flavor profile stored as `JSONB` on the same row
- `recipe` — 102 IBA cocktails with `(name, iba_category, method, glass, garnish)`
- `recipe_ingredient` — many-to-many recipe→class with `(amount, unit, is_optional, alternative_group_id)`

Bottle ordering note: `BOTTLES_LIST` orders by `(ic.name, b.brand, b.label NULLS FIRST, b.id)`. The label and id tiebreakers were added because UMAP on `/inventory/flavor-map` is order-sensitive, and the original `(class, brand)` ordering let Postgres return same-brand rows in arbitrary physical order — so `limit=100` vs `limit=200` callers got different cluster partitions.

## Common Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| 503 Service Unavailable | DB not reachable | Verify `DATABASE_URL` and Postgres is running |
| 422 Validation Error on POST | Flavor profile has invalid value | Ensure all 16 dimensions are 0–5 |
| 404 Not Found | Recipe/bottle doesn't exist | Check ID is correct |

---

See [root README](../README.md) for full project overview, quick start, and how to add your own bottles.
