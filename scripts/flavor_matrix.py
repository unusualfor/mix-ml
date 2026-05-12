"""Generate pairwise flavor-distance matrix, heatmap, and cluster report.

Usage (from repo root, with backend venv active)::

    PYTHONPATH=backend python scripts/flavor_matrix.py
    PYTHONPATH=backend python scripts/flavor_matrix.py --cluster-threshold 0.30
    PYTHONPATH=backend python scripts/flavor_matrix.py --db-url 'postgresql+psycopg://...'
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import textwrap
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # non-interactive backend — must be before pyplot
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.cluster.hierarchy import average, fcluster, leaves_list, linkage
from scipy.spatial.distance import squareform
from sqlalchemy import create_engine, text

# ---------------------------------------------------------------------------
# Ensure the backend package is importable when invoked from repo root.
# ---------------------------------------------------------------------------
_BACKEND_DIR = str(Path(__file__).resolve().parent.parent / "backend")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from app.services.flavor import flavor_distance  # noqa: E402

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------
CLUSTER_THRESHOLD = 0.25
ANOMALY_THRESHOLD = 0.30
INTER_CLUSTER_TOP_N = 10
OUTPUT_DIR = Path(__file__).resolve().parent / "output"

QUERY = text("""
    SELECT b.id, b.brand, b.label, ic.name AS class_name, b.flavor_profile
    FROM bottle b
    JOIN ingredient_class ic ON ic.id = b.class_id
    ORDER BY ic.name, b.brand, b.label
""")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _display_name(row: dict) -> str:
    parts = [row["brand"]]
    if row["label"]:
        parts.append(row["label"])
    return " ".join(parts)


def _truncate(s: str, n: int = 20) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


# ---------------------------------------------------------------------------
# data loading
# ---------------------------------------------------------------------------

def load_bottles(db_url: str) -> list[dict]:
    engine = create_engine(db_url)
    with engine.connect() as conn:
        rows = conn.execute(QUERY).mappings().all()
    engine.dispose()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# matrix computation
# ---------------------------------------------------------------------------

def compute_matrix(bottles: list[dict]) -> tuple[list[str], np.ndarray]:
    n = len(bottles)
    names = [_display_name(b) for b in bottles]
    mat = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            d = flavor_distance(
                bottles[i]["flavor_profile"],
                bottles[j]["flavor_profile"],
            )
            mat[i, j] = d
            mat[j, i] = d
    return names, mat


# ---------------------------------------------------------------------------
# output 1 — CSV
# ---------------------------------------------------------------------------

def write_csv(names: list[str], mat: np.ndarray, path: Path) -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([""] + names)
        for i, name in enumerate(names):
            w.writerow([name] + [f"{mat[i, j]:.3f}" for j in range(len(names))])


# ---------------------------------------------------------------------------
# output 2 — heatmap PNG (clustered)
# ---------------------------------------------------------------------------

def write_heatmap(
    names: list[str], mat: np.ndarray, path: Path, *, method: str = "average"
) -> list[int]:
    """Write clustered heatmap and return the leaf order."""
    condensed = squareform(mat, checks=False)
    Z = linkage(condensed, method=method)
    order = list(leaves_list(Z))

    reordered = mat[np.ix_(order, order)]
    labels = [_truncate(names[i]) for i in order]

    fig, ax = plt.subplots(figsize=(16, 16), dpi=150)
    sns.heatmap(
        pd.DataFrame(reordered, index=labels, columns=labels),
        annot=True,
        fmt=".2f",
        annot_kws={"size": 6},
        cmap="viridis",
        vmin=0,
        vmax=1,
        linewidths=0.3,
        square=True,
        ax=ax,
    )
    ax.set_title(
        f"Flavor Distance Matrix — {len(names)} bottles (clustered)",
        fontsize=14,
        pad=12,
    )
    plt.xticks(rotation=45, ha="right", fontsize=7)
    plt.yticks(rotation=0, fontsize=7)
    plt.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return order


# ---------------------------------------------------------------------------
# output 3 — cluster report
# ---------------------------------------------------------------------------

def write_cluster_report(
    bottles: list[dict],
    names: list[str],
    mat: np.ndarray,
    path: Path,
    threshold: float,
) -> None:
    n = len(bottles)
    condensed = squareform(mat, checks=False)
    Z = linkage(condensed, method="average")
    labels = fcluster(Z, t=threshold, criterion="distance")

    # group bottles by cluster
    clusters: dict[int, list[int]] = {}
    for idx, cid in enumerate(labels):
        clusters.setdefault(cid, []).append(idx)

    lines: list[str] = []
    lines.append(f"=== HIERARCHICAL CLUSTERS (threshold={threshold}) ===")
    lines.append(f"Number of clusters found: {len(clusters)}")
    lines.append("")

    # per-cluster details
    cluster_ids_sorted = sorted(clusters, key=lambda c: -len(clusters[c]))
    for rank, cid in enumerate(cluster_ids_sorted, 1):
        members = clusters[cid]
        lines.append(f"--- Cluster {rank} ({len(members)} bottle{'s' if len(members) != 1 else ''}) ---")

        # internal mean distance
        if len(members) > 1:
            dists = [
                mat[i, j]
                for ii, i in enumerate(members)
                for j in members[ii + 1 :]
            ]
            mean_d = sum(dists) / len(dists)
            lines.append(f"Internal mean distance: {mean_d:.2f}")
        else:
            lines.append("Internal mean distance: n/a (singleton)")

        lines.append("Bottles:")
        for idx in members:
            b = bottles[idx]
            label_part = f" — {b['label']}" if b["label"] else ""
            lines.append(f"  • {b['brand']}{label_part} ({b['class_name']})")
        lines.append("")

    # inter-cluster nearest pairs
    lines.append("=== INTER-CLUSTER NEAREST PAIRS ===")
    lines.append("Top pairs across different clusters:")

    pairs: list[tuple[float, int, int]] = []
    for i in range(n):
        for j in range(i + 1, n):
            if labels[i] != labels[j]:
                pairs.append((mat[i, j], i, j))
    pairs.sort()

    cid_to_rank = {cid: rank for rank, cid in enumerate(cluster_ids_sorted, 1)}
    for k, (d, i, j) in enumerate(pairs[:INTER_CLUSTER_TOP_N], 1):
        ri, rj = cid_to_rank[labels[i]], cid_to_rank[labels[j]]
        lines.append(
            f"  {k:>2}. {names[i]} → {names[j]}  "
            f"(distance {d:.3f}) [Cluster {ri} → Cluster {rj}]"
        )
    lines.append("")

    # anomalies
    lines.append("=== ANOMALIES ===")
    lines.append(
        f"Bottles with internal mean distance to own cluster > {ANOMALY_THRESHOLD:.2f}:"
    )
    found_anomaly = False
    for idx in range(n):
        cid = labels[idx]
        peers = [j for j in clusters[cid] if j != idx]
        if not peers:
            continue
        mean_d = sum(mat[idx, j] for j in peers) / len(peers)
        if mean_d > ANOMALY_THRESHOLD:
            found_anomaly = True
            rank = cid_to_rank[cid]
            lines.append(
                f"  • {names[idx]} in Cluster {rank} "
                f"— internal mean {mean_d:.2f}"
            )
    if not found_anomaly:
        lines.append("  (none)")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate pairwise flavor-distance matrix and cluster analysis."
    )
    parser.add_argument(
        "--db-url",
        default=os.environ.get("DATABASE_URL", ""),
        help="SQLAlchemy database URL (default: $DATABASE_URL)",
    )
    parser.add_argument(
        "--cluster-threshold",
        type=float,
        default=CLUSTER_THRESHOLD,
        help=f"Distance threshold for flat clustering (default: {CLUSTER_THRESHOLD})",
    )
    args = parser.parse_args()

    if not args.db_url:
        print("ERROR: provide --db-url or set DATABASE_URL", file=sys.stderr)
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Connecting to DB …")
    bottles = load_bottles(args.db_url)
    print(f"Loaded {len(bottles)} bottles")

    print("Computing distance matrix …")
    names, mat = compute_matrix(bottles)

    csv_path = OUTPUT_DIR / "flavor_matrix.csv"
    write_csv(names, mat, csv_path)
    print(f"CSV  → {csv_path}")

    print("Generating clustered heatmap …")
    order = write_heatmap(names, mat, OUTPUT_DIR / "flavor_matrix.png")
    print(f"PNG  → {OUTPUT_DIR / 'flavor_matrix.png'}")

    print("Generating cluster report …")
    write_cluster_report(
        bottles, names, mat, OUTPUT_DIR / "flavor_clusters.txt", args.cluster_threshold
    )
    print(f"TXT  → {OUTPUT_DIR / 'flavor_clusters.txt'}")

    print("Done.")


if __name__ == "__main__":
    main()
