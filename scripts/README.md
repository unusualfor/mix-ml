# Scripts & Tools

Offline tools for building, analyzing, and calibrating the mix-ml platform.

**For overview, quick start, and full workflow, see the [root README](../README.md).**

## Overview

```
scripts/
├── add-bottle.sh              # One-command add-a-bottle (primary entry point)
├── regen-flavor-map.sh        # Re-cluster only (no DB write)
├── scrape_iba.py              # Download all 102 IBA recipes from iba-world.com
├── analyze_iba.py             # Generate descriptive reports from recipes
├── generate_seed_sql.py       # Build seed.sql from bottles_seed.json + IBA JSON
├── calibrate_clusters.py      # Host-side calibrator (used when no stack is running)
├── flavor_matrix.py           # Offline pairwise flavor distance heatmap
├── requirements-scripts.txt   # Dependencies: scipy, numpy, scikit-learn
├── data/
│   ├── bottles_seed.json           # Your bottle inventory (source of truth)
│   ├── iba_cocktails.json          # Raw scraper output
│   ├── iba_cocktails_normalized.json
│   └── taxonomy_classes.csv
├── output/                    # Transient files (gitignored)
└── seed.sql                   # Generated database seed
```

## Add a Bottle (Primary Workflow)

With the stack running (`docker compose up -d`):

```bash
# 1. Write the new bottle as a single-object JSON (see schema in the root README).
# 2. Run the orchestrator:
./scripts/add-bottle.sh /tmp/new_bottle.json
```

The script appends to `bottles_seed.json`, upserts via `/api/bottles/_bulk` (no `down -v`), triggers a frontend regenerate, runs `python -m app._tools.calibrate` inside the frontend container, refreshes the bind-mounted `cluster_impressions.json`, surfaces TODO clusters, and prints the suggested git commit. It does **not** auto-commit. Pass `--regen-seed` to also rewrite `scripts/seed.sql` and `db/seed.sql`.

Re-cluster without a DB change:

```bash
./scripts/regen-flavor-map.sh
```

## Cold-start Seed Generation

When you want a fresh DB seeded directly from `bottles_seed.json` (instead of replaying the API):

```bash
cd scripts
python generate_seed_sql.py data/iba_cocktails_normalized.json   # reads bottles_seed.json automatically
cp seed.sql ../db/seed.sql
docker compose down -v && docker compose up -d
```

The seed SQL is idempotent — safe to re-load.

## Tuning DBSCAN

If clustering looks wrong, run the in-container calibrator with different params:

```bash
docker exec --user 0 mix-ml-frontend \
    python -m app._tools.calibrate \
        --backend-url http://backend:8080 \
        --eps 0.7 --min-samples 2 --write
```

Typical `eps` range for 30–80 bottles: 0.4–0.8. Larger `eps` → fewer, bigger clusters.

The host-side `calibrate_clusters.py` is kept as a fallback for the no-stack case. **Prefer the in-container path** — `scikit-learn` minor versions can change DBSCAN cluster IDs even with identical input, and the container pins the exact versions the frontend renders against (sklearn 1.8.0, umap-learn 0.5.12).

## Scraper

Download all 102 IBA recipes from [iba-world.com](https://iba-world.com):

```bash
python scrape_iba.py
# Output: data/iba_cocktails.json

# Idempotent — skips recipes already present
```

**Output format:**
```json
{
  "name": "Margarita",
  "category": "contemporary",
  "ingredients": [
    {"amount": 45, "unit": "ml", "name": "Tequila"},
    {"amount": 30, "unit": "ml", "name": "Cointreau"}
  ],
  "method": "Shake with ice and strain",
  "garnish": "Lime wheel"
}
```

## Analyzer

Generate descriptive reports from IBA recipes:

```bash
python analyze_iba.py data/iba_cocktails.json
```

**Output files:**
- `report_ingredient_frequency.csv` — ingredient frequency + recipe lists
- `report_unit_inventory.csv` — units of measure (ml, dash, bar spoon, etc.)
- `report_amount_anomalies.txt` — null/zero/non-numeric amounts
- `report_ingredient_clusters.txt` — name-similarity groups (merge candidates)
- `report_summary.md` — overview (categories, top-20 ingredients, techniques)

No dependencies beyond Python stdlib.

## Flavor Matrix (Advanced)

Offline computation of N×N flavor distance matrix with clustering visualization:

```bash
# Requires backend venv + scientific deps
cd backend && source .venv/bin/activate
pip install -r ../scripts/requirements-scripts.txt

# Run from repo root with live backend
PYTHONPATH=backend \
BACKEND_URL="http://localhost:8080" \
python scripts/flavor_matrix.py
```

**Options:**
- `--backend-url URL` (default from env var)
- `--cluster-threshold 0.25` (distance cut-off for clustering)
- `--output-dir output/` (where to save results)

**Output (in `output/`, gitignored):**
- `flavor_matrix.csv` — N×N symmetric distance matrix
- `flavor_matrix.png` — clustered heatmap visualization
- `flavor_clusters.txt` — cluster membership + inter-cluster bridges

---

See [root README](../README.md) for full workflow, quick start, and calibration details.
