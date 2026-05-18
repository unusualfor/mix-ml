# Scripts & Tools

Offline tools for building, analyzing, and calibrating the mix-ml platform.

**For overview, quick start, and full workflow, see the [root README](../README.md).**

## Overview

```
scripts/
├── scrape_iba.py              # Download all 102 IBA recipes from iba-world.com
├── analyze_iba.py             # Generate descriptive reports from recipes
├── generate_seed_sql.py       # Build seed.sql from normalized JSON + bottles
├── calibrate_clusters.py      # Tune DBSCAN, match cluster impressions
├── flavor_matrix.py           # Offline pairwise flavor distance heatmap
├── requirements-scripts.txt   # Dependencies: scipy, numpy, scikit-learn
├── data/
│   ├── bottles_seed.json           # Your bottle inventory (EDIT THIS)
│   ├── iba_cocktails.json          # Raw scraper output
│   ├── iba_cocktails_normalized.json
│   └── taxonomy_classes.csv
├── output/                    # Transient files (gitignored)
└── seed.sql                   # Generated database seed
```

## Seed Generation (Main Workflow)

To update your bottle collection:

```bash
# 1. Edit bottles_seed.json with your bottles
vim scripts/data/bottles_seed.json

# 2. Regenerate seed.sql
cd scripts
python generate_seed_sql.py data/bottles_seed.json data/iba_cocktails_normalized.json

# 3. Update database
cp seed.sql ../db/seed.sql
docker compose down -v && docker compose up -d
```

The seed SQL is idempotent — safe to run multiple times.

## Calibration (After Major Bottle Changes)

When you add/remove many bottles, UMAP and DBSCAN will discover different clusters. Recalibrate:

```bash
# Start backend if not already running
docker compose up -d backend

# Generate new cluster compositions (preserves existing impressions where possible)
python calibrate_clusters.py --backend-url http://localhost:8080 --write

# Edit cluster_impressions.json: replace "TODO" lines with real descriptions
# Example: "Extreme botanicals" instead of "TODO: Cluster 0"

# Rebuild frontend to load new impressions
docker compose up -d --build frontend
```

To tune DBSCAN if clusters look wrong:

```bash
python calibrate_clusters.py --eps 0.7 --backend-url http://localhost:8080 --write
```

Typical `eps` range for 30–80 bottles: 0.4–0.8. Larger = fewer clusters.

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
