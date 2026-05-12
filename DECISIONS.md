# Mix-ML — Architecture & Decisions

A cocktail intelligence platform built on the 102 official IBA recipes.
Scrapes, normalizes, stores, and serves cocktail data through a REST API
with a feasibility engine that answers _"what can I make right now?"_.

---

## Project Phases

| Tag | Phase | What shipped |
|-----|-------|--------------|
| — | 0 – Scrape | `scrape_iba.py` → `iba_cocktails.json` (102 recipes) |
| — | 1 – Analyze | `analyze_iba.py` → 5 CSV/MD reports, cluster detection |
| — | 2 – Seed | `generate_seed_sql.py` → DDL + 178 classes, 102 recipes, 424 ingredients |
| — | 3 – Deploy | Kustomize manifests → PostgreSQL 16 on OpenShift Local (CRC) |
| — | 4 – API (read) | FastAPI: `/api/classes`, `/api/recipes` |
| — | 5 – Bottles | CRUD + bulk upsert for personal bottle inventory |
| `v0.3` | 6 – Feasibility | `can-make-now`, per-recipe feasibility, commodity ingredients |

---

## Stack

| Layer | Choice | Why |
|-------|--------|-----|
| Language | Python 3.11+ | Single language across scraper, analyzer, API |
| Web framework | FastAPI | Async-capable, Pydantic validation, auto OpenAPI docs |
| ORM layer | SQLAlchemy 2.0 **sync** + raw `text()` | Full SQL control; no ORM models — the schema is simple enough that mapped classes add indirection without value |
| DB driver | `psycopg` 3 | Native async support if needed later; modern replacement for psycopg2 |
| Validation | Pydantic v2 | Request/response models, settings via `pydantic-settings` |
| Database | PostgreSQL 16 (`sclorg/postgresql-16-c9s`) | JSONB for flavor profiles, CTEs for hierarchy queries, CHECK constraints |
| Container platform | OpenShift Local (CRC) | Single-node cluster for local development; same API as production OpenShift |
| Manifests | Kustomize (base + overlay) | No Helm templating overhead; overlays handle CRC-specific resource limits |
| Tests | pytest + `TestClient` | Session-scoped schema isolation, no mocking needed |

---

## Data Decisions

### D1 — Ingredient taxonomy is a two-level tree, not a flat list

```
Whiskey (parent)
├── Bourbon (generic)
├── Rye Whiskey
├── Irish Whiskey
└── …
```

IBA recipes reference raw ingredient names like _"Gin"_ or _"Sweet Red Vermouth"_.
A flat list would require exact name matches.
The two-level hierarchy (19 parent families + 159 children + 10 garnishes = 178 classes)
lets the feasibility engine answer: _"I don't have Bourbon, but I have Rye Whiskey —
they're siblings under Whiskey, does a `(generic)` recipe accept either?"_

A deeper tree (genus → species → sub-species) was considered and rejected:
IBA recipes don't have enough granularity to justify it,
and it would complicate the sibling-expansion logic.

### D2 — `(generic)` classes enable loose matching

Some recipes call for _"Gin"_ without specifying a style.
These map to `Gin (generic)` in the taxonomy.
The feasibility engine treats `(generic)` classes specially:
any sibling under the same parent satisfies the requirement.

**Example:** _Negroni_ calls for `Gin (generic)`.
A bottle of _London Dry Gin_ (sibling) satisfies it.
A bottle of _Old Tom Gin_ (sibling) also satisfies it.
But a bottle of _Tequila Blanco_ does not (different parent).

### D3 — Commodity ingredients are always available

35 ingredient classes are marked `is_commodity = TRUE`:
sodas, fresh juices, sugars, syrups, eggs, cream, coffee, salt, water.
These are pantry staples you can buy at any supermarket —
the feasibility engine treats them as always on-hand,
so _"Americano"_ (Campari + Vermouth Rosso + **Soda Water**) doesn't fail
just because you didn't register a bottle of sparkling water.

**Commodity categories:**

| Group | Examples |
|-------|----------|
| Carbonated mixers | Soda Water, Tonic Water, Ginger Beer, Cola |
| Fresh juices | Lemon, Lime, Orange, Pineapple, Grapefruit, Cranberry, Tomato |
| Sugars | Sugar, Sugar Cube, Demerara Sugar, Vanilla Sugar |
| Syrups | Simple Syrup, Honey Syrup, Honey Mix, Raw Honey |
| Dairy & eggs | Egg White, Egg Yolk, Cream, Coconut Cream |
| Pantry | Salt, Cloves, Vanilla Extract, Water, Worcestershire Sauce |
| Coffee | Espresso, Hot Coffee |

### D4 — Garnishes are tracked but never block feasibility

Every garnish class has `is_garnish = TRUE`.
The feasibility engine skips them entirely.
They still appear in the `/feasibility` detail endpoint
so the UI can display _"you'll also need a lemon wheel"_.

### D5 — Alternative groups model OR-relationships

Some recipes allow substitution: _"Gin OR Vodka"_.
These share an `alternative_group_id` within the same recipe.
The feasibility engine treats the group as satisfied
if **any** class in the group is on-hand.

### D6 — Flavor profiles use a fixed 16-key schema

```json
{"sweet": 3, "bitter": 4, "sour": 1, "citrusy": 2, "fruity": 1,
 "herbal": 3, "floral": 1, "spicy": 0, "smoky": 0, "vanilla": 0,
 "woody": 1, "minty": 0, "earthy": 0, "umami": 0, "body": 4, "intensity": 4}
```

Each key is 0–5. The schema is enforced by Pydantic on input
and stored as JSONB.  Keys are English (not Italian)
for consistency with the IBA source data.
The fixed schema avoids sparse vectors and makes future ML features
(taste-similarity, recommendation) straightforward.

---

## API Decisions

### D7 — Raw SQL via `text()` instead of ORM models

All queries live in [backend/app/queries.py](backend/app/queries.py) as `text()` objects.
The schema has 4 tables with simple joins — an ORM layer would add
a mapping step without reducing complexity.
Raw SQL also makes it trivial to tune queries, add CTEs,
and use Postgres-specific features like `CAST(:x AS text)`.

### D8 — Centralized query module

Every SQL statement is in `queries.py`.
Routers and services import query objects by name.
This avoids SQL scattered across route handlers
and makes it easy to audit all database access in one file.

### D9 — Feasibility is computed in Python, not SQL

The feasibility engine (`services/feasibility.py`) loads all required ingredients
in one query, then evaluates them in Python with dict lookups.
A pure-SQL approach (recursive CTEs + lateral joins) was considered
but would be harder to extend with the `(generic)` sibling expansion
and commodity skipping logic.

The trade-off: one extra round-trip for class hierarchy data.
At 178 classes and 102 recipes, this is negligible.

### D10 — Two feasibility endpoints serve different needs

| Endpoint | Purpose | Performance |
|----------|---------|-------------|
| `GET /api/cocktails/can-make-now` | List view: all recipes with can/cannot status | Single pass over all recipes; filters by status, category, max_missing |
| `GET /api/cocktails/{id}/feasibility` | Detail view: per-ingredient breakdown with matching bottles | One recipe at a time; includes bottle-level detail |

The list endpoint powers dashboard views.
The detail endpoint powers recipe cards.

### D11 — Bottle CRUD supports bulk upsert

`POST /api/bottles/bulk` accepts an array and uses brand+label as a
natural key for upsert. This enables seeding from `bottles_seed.json`
(42 bottles) in one call without worrying about duplicates on re-run.

---

## Infrastructure Decisions

### D12 — Kustomize over Helm

The deployment has one database (Postgres) and one job (seed).
Helm's templating engine and chart lifecycle are overkill.
Kustomize's base/overlay model handles the only variation needed:
resource limits for CRC's constrained environment.

### D13 — Seed job is idempotent

The `seed-job.yaml` runs `psql -f seed.sql` wrapped in a check:

```
if table ingredient_class has rows → exit 0 (already seeded)
else → run seed.sql
```

This means `oc apply -k` is always safe to re-run.
For schema changes, `db/migrations/` holds numbered migration files
(e.g., `001_add_commodity_flag.sql`).

### D14 — WSL ↔ CRC connectivity via kubectl + kubeconfig

CRC runs on Windows. `oc port-forward` from WSL would use the Windows
`oc.exe`, which binds to Windows localhost — unreachable from WSL.
Instead, native Linux `kubectl` with the CRC kubeconfig file
(`/mnt/c/Users/.../kubeconfig`) binds to WSL localhost correctly.

---

## Test Decisions

### D15 — Schema isolation via `search_path`

Tests create a `test_cocktail` schema with its own tables and seed data.
Two SQLAlchemy event listeners (`connect` + `checkout`) set
`SET search_path TO test_cocktail` on every connection,
ensuring tests never touch the public schema.

The schema is created once per session (session-scoped fixture)
and dropped at teardown.

### D16 — No mocking — tests hit a real database

Every test runs real SQL against Postgres.
This catches query syntax errors, constraint violations,
and type mismatches that mocked tests would miss.
The test schema makes this fast (6 classes, 4 recipes, 9 ingredients).

### D17 — Test data is minimal but complete

The test seed covers all edge cases with minimal data:

| Scenario | Test data |
|----------|-----------|
| Parent → children hierarchy | TestSpirit → TestGin, TestVodka, TestBitters |
| Garnish | TestGarnish → TestLemonWheel |
| Commodity | TestMixer → TestSodaWater, TestOrangeJuice |
| Mandatory ingredients | Test Negroni: TestGin + TestVodka |
| Optional ingredients | Test Negroni: TestBitters (optional) |
| Garnish ingredients | Test Negroni: TestLemonWheel (garnish) |
| Alternative groups | Test Mule: TestGin OR TestVodka (alt_group=1) |
| Spirit + commodity | Test Spritz: TestGin + TestSodaWater |
| All-commodity recipe | Test Juice Mix: TestSodaWater + TestOrangeJuice |

---

## File Map

```
mix-ml/
├── scrape_iba.py                  # Phase 0: IBA website → JSON
├── iba_cocktails.json             # Raw scraped data (102 recipes)
├── analyze_iba.py                 # Phase 1: frequency, clusters, anomalies
├── report_*.{csv,md,txt}          # Analysis output
├── iba_cocktails_normalized.json  # Cleaned data with class mappings
├── taxonomy_classes.csv           # Class taxonomy reference
├── generate_seed_sql.py           # Phase 2: JSON → seed.sql
├── seed.sql                       # Generated DDL + INSERTs
├── bottles_seed.json              # 42 personal bottles with flavor profiles
├── db/
│   ├── seed.sql                   # Copy for deploy
│   └── migrations/
│       └── 001_add_commodity_flag.sql
├── manifests/                     # Phase 3: Kustomize for CRC
│   ├── base/                      #   namespace, PVC, deployment, service, job
│   └── overlays/crc/              #   resource limit patches
└── backend/                       # Phase 4–6: FastAPI application
    ├── app/
    │   ├── main.py                #   App factory, JSON logging
    │   ├── config.py              #   pydantic-settings (DATABASE_URL, pool)
    │   ├── db.py                  #   Engine, SessionLocal, get_db
    │   ├── models.py              #   Pydantic request/response models
    │   ├── queries.py             #   All SQL in one place
    │   ├── routers/
    │   │   ├── health.py          #   /healthz, /readyz
    │   │   ├── classes.py         #   /api/classes (tree + flat)
    │   │   ├── recipes.py         #   /api/recipes (list + detail)
    │   │   ├── bottles.py         #   /api/bottles (CRUD + bulk)
    │   │   └── cocktails.py       #   /api/cocktails (feasibility)
    │   └── services/
    │       └── feasibility.py     #   can-make-now engine
    └── tests/                     #   30 tests, schema-isolated
        ├── conftest.py
        ├── test_health.py
        ├── test_classes.py
        ├── test_recipes.py
        ├── test_bottles.py
        └── test_cocktails.py
```

---

## Current Numbers

| Metric | Value |
|--------|-------|
| IBA recipes | 102 |
| Ingredient classes | 178 (19 parents + 159 children) |
| Garnish classes | 10 |
| Commodity classes | 35 |
| Recipe ingredients | 424 |
| Personal bottles | 42 |
| Feasible cocktails | 15 (with 42 bottles + commodities) |
| Tests | 30 passing |
