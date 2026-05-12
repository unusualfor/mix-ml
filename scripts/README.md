# Scripts

Pipeline tools and offline analysis. All scripts live here along with their
input data (`data/`) and generated reports (`reports/`).

## Structure

```
scripts/
├── scrape_iba.py              # IBA recipe scraper
├── analyze_iba.py             # Descriptive reports from scraped JSON
├── generate_seed_sql.py       # Builds seed.sql from normalized JSON + taxonomy
├── flavor_matrix.py           # Offline pairwise flavor-distance heatmap
├── requirements-scripts.txt   # Scientific deps for flavor_matrix.py
├── data/
│   ├── iba_cocktails.json           # Raw scraper output (102 recipes)
│   ├── iba_cocktails_normalized.json # Normalized ingredient names
│   ├── taxonomy_classes.csv         # Ingredient class taxonomy
│   └── bottles_seed.json           # Personal bottle inventory seed
├── reports/
│   ├── report_ingredient_frequency.csv
│   ├── report_unit_inventory.csv
│   ├── report_amount_anomalies.txt
│   ├── report_ingredient_clusters.txt
│   └── report_summary.md
├── output/                    # flavor_matrix.py output (gitignored)
└── seed.sql                   # Generated seed SQL (canonical copy in db/)
```

## Scraper

```bash
cd scripts
python scrape_iba.py
# Output: data/iba_cocktails.json (idempotent — skips existing recipes)
```

## Analyzer

```bash
cd scripts
python analyze_iba.py data/iba_cocktails.json
# Output: 5 reports in current directory
```

## Seed Generator

```bash
cd scripts
python generate_seed_sql.py data/iba_cocktails_normalized.json
# Output: seed.sql in current directory
```

## Flavor Matrix

Requires the backend virtualenv and scientific dependencies.

```bash
cd backend && source .venv/bin/activate
pip install -r ../scripts/requirements-scripts.txt

# From repo root, with port-forward to DB
PYTHONPATH=backend \
DATABASE_URL="postgresql+psycopg://cocktailuser:<password>@localhost:5432/cocktails" \
python scripts/flavor_matrix.py
```

Optional flags:

| Flag | Default | Description |
|------|---------|-------------|
| `--db-url` | `$DATABASE_URL` | SQLAlchemy connection string |
| `--cluster-threshold` | `0.25` | Distance cut-off for flat clustering |

Outputs (in `scripts/output/`, gitignored):

| File | Description |
|------|-------------|
| `flavor_matrix.csv` | N×N symmetric distance matrix |
| `flavor_matrix.png` | Clustered heatmap (hierarchical, average linkage) |
| `flavor_clusters.txt` | Cluster membership, inter-cluster bridges, anomalies |
