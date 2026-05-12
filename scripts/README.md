# Scripts

Offline analysis tools. Require the backend virtualenv and scientific
dependencies listed in `requirements-scripts.txt`.

## Setup

```bash
cd backend
source .venv/bin/activate
pip install -r ../scripts/requirements-scripts.txt
```

## flavor_matrix.py

Generates a pairwise flavor-distance matrix across all bottles in the DB.

```bash
# From repo root, with backend venv active + port-forward to DB
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
