# Mix-ML Backend API

REST API for the IBA cocktail database, built on FastAPI + SQLAlchemy + psycopg 3.

## Local Setup

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Port-forward to CRC DB (bind 0.0.0.0 for WSL2)
oc port-forward svc/postgres 5432:5432 -n cocktail-db --address 0.0.0.0 &

# Use the Windows host IP from WSL2
export DATABASE_URL="postgresql+psycopg://cocktailuser:<password>@$(grep nameserver /etc/resolv.conf | awk '{print $2}'):5432/cocktails"
uvicorn app.main:app --reload
```

API available at `http://localhost:8000`. Interactive docs: `http://localhost:8000/docs`.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/healthz` | Liveness probe |
| GET | `/readyz` | Readiness probe (checks DB) |
| GET | `/api/classes` | Ingredient taxonomy (tree or `?flat=true`) |
| GET | `/api/recipes` | Recipe list with `?category=`, `?search=`, `?limit=`, `?offset=` |
| GET | `/api/recipes/{id}` | Recipe detail with ingredients |
| GET | `/api/recipes/by-name?name=` | Recipe detail by name (case-insensitive) |
| GET | `/api/recipes/{id}/substitutions` | Substitutes for missing ingredients |
| GET | `/api/bottles` | Personal bottle inventory |
| GET | `/api/bottles/{id}` | Bottle detail |
| POST | `/api/bottles` | Create bottle |
| POST | `/api/bottles/bulk` | Bulk upsert bottles |
| PUT | `/api/bottles/{id}` | Update bottle |
| DELETE | `/api/bottles/{id}` | Delete bottle |
| GET | `/api/cocktails/can-make-now` | Feasible recipes with current inventory |
| GET | `/api/cocktails/{id}/feasibility` | Per-recipe feasibility detail |
| GET | `/api/cocktails/optimize-next` | Next bottle that unlocks the most recipes |
| GET | `/api/bottles/optimize-shopping` | ILP-based multi-step shopping plan |
| GET | `/api/bottles/optimize-shopping/verify` | Sanity check: ILP vs greedy |
| GET | `/api/flavor/distance` | Flavor distance between two bottles |
| GET | `/api/flavor/similar-bottles` | Bottles ranked by similarity to a pivot |
| GET | `/api/flavor/substitution-trace` | Detailed substitution logic debug |

## Tests

```bash
# Requires a reachable Postgres DB (port-forward or local)
export DATABASE_URL="postgresql+psycopg://cocktailuser:<password>@localhost:5432/cocktails"
pytest tests/ -v   # 104 tests
```

Tests create a temporary `test_cocktail` schema, insert minimal data, and drop it after the session.

## Assumed-Available Ingredients

The `is_commodity` flag on `ingredient_class` marks ingredients that
the system assumes are always available without requiring them to be
tracked as `bottle` entries. This includes two semantic categories
sharing the same flag for implementation simplicity:

1. **True commodities**: low-cost consumables typically present in
   any kitchen (fresh citrus juices, soda water, sugar, eggs, cream,
   syrups preparable in 2 minutes).
2. **Assumed-available alcoholics**: items the home bar owner
   considers always at hand for hosting purposes, even though they
   are bottled spirits/wines with non-trivial cost (Champagne,
   Prosecco, Red Wine, Dry White Wine).

To track Champagne or Prosecco as actual inventoried bottles (e.g.
distinguishing brut vs demi-sec), the user would need to either:
(a) re-flag the class as non-commodity via SQL, or
(b) introduce a more granular class (e.g. "Brut Champagne",
"Demi-Sec Champagne") with the parent class remaining commodity for
backward compatibility.

## Flavor Distance

The `flavor_distance` metric computes a weighted Euclidean distance between
two 16-dimensional `flavor_profile` vectors (values 0–5). The space is split into:

- **Gustative** (14 dims): sweet, bitter, sour, citrusy, fruity,
  herbal, floral, spicy, smoky, vanilla, woody, minty, earthy, umami
- **Structural** (2 dims): body, intensity

Each sub-distance is normalized to [0, 1], then combined:

$$d = w_g \cdot d_{\text{gustative}} + w_s \cdot d_{\text{structural}}$$

Default weights: $w_g = 0.7$, $w_s = 0.3$ ($w_g + w_s = 1$).

### Diagnostic endpoint

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/flavor/distance?bottle_a=<id>&bottle_b=<id>` | Distance breakdown between two bottles |

Optional params: `gustative_weight`, `structural_weight`.
Errors: 404 if a bottle doesn't exist, 422 if weights don't sum to 1.

## Similarity & Substitution

Two complementary endpoints based on `flavor_distance`:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/flavor/similar-bottles?bottle_id=<id>` | Bottles ranked by distance from a pivot |
| GET | `/api/recipes/{id}/substitutions` | Substitutes for missing (and satisfied) ingredients |
| GET | `/api/flavor/substitution-trace?recipe_id=<id>&recipe_ingredient_id=<id>` | Full substitution logic debug |

### Similar Bottles

Params: `top` (default 10), `max_distance`, `same_family_only`.
Returns nearest bottles to the pivot with `top_shared_dimensions` and
`top_differing_dimensions` to explain similarity.

### Substitutions

For each `recipe_ingredient` (including satisfied ones):
1. Computes a **pivot profile** from the required class (or siblings)
2. Excludes **anti-duplicate** bottles (classes already used in the recipe)
3. Excludes already-owned satisfying bottles from candidates
4. Ranks by **tier**: `strict` (same family, ≤ 0.25) or
   `loose` (cross-family, ≤ 0.20)

Params: `tier=strict|loose|both`, `strict_threshold`, `loose_threshold`,
`include_satisfied`.

## Multi-step Shopping Optimization

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/bottles/optimize-shopping?budget=K` | ILP-based K-bottle shopping plan |
| GET | `/api/bottles/optimize-shopping/verify` | Sanity check: ILP(K=1) vs greedy |

Evolution of the `optimize-next` endpoint (greedy K=1): given a budget of K
bottles (max 15), a CP-SAT solver (Google OR-Tools) finds the purchase set
that maximizes the weighted count of feasible IBA recipes.

**ILP model**: boolean variables `x_c` (buy class c?), `y_r` (recipe r
becomes feasible?). Constraints: `sum(x) ≤ budget`; for each unsatisfied
requirement of r: `y_r ≤ sum(x_c)` where c can satisfy it (strict match +
wildcard generic). Objective: `max sum(weight[cat] × y_r)`.

**Params**: `budget` (1–15), `weight_unforgettable/contemporary/new_era`
(default 1.0), `explain` (false), `solver_timeout_seconds` (30).

**`?explain=true`**: adds `newly_feasible_recipes` (with `covered_by_purchases`)
and `purchases_marginal_value` (post-hoc greedy decomposition of the optimal plan).

**`/verify`**: compares ILP(K=1) with greedy. If `match: false`, the ILP
modeling diverges from feasibility logic — indicates a bug.

**Timeout**: if the solver doesn't converge, returns best-incumbent with
`is_optimal: false`, `solver_status: "FEASIBLE"`.

## Container Build

```bash
podman build -t mix-ml-backend:latest backend/
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+psycopg://cocktailuser:changeme@localhost:5432/cocktails` | SQLAlchemy connection string |
| `LOG_LEVEL` | `INFO` | Log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
