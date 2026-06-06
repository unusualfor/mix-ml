#!/usr/bin/env python3
"""Calibrate 2D flavor map clusters and generate impression templates.

Runs UMAP + DBSCAN on the current bottle inventory (via backend API)
and outputs cluster compositions as JSON — ready for writing impressions.

Usage:
    # Against running backend (default http://localhost:8080)
    python scripts/calibrate_clusters.py

    # Custom backend URL
    python scripts/calibrate_clusters.py --backend-url http://172.25.144.1:8080

    # Override DBSCAN parameters
    python scripts/calibrate_clusters.py --eps 0.6 --min-samples 2

    # Write output directly to the impressions file
    python scripts/calibrate_clusters.py --write

Output:
    Prints cluster compositions to stdout (JSON).
    With --write, overwrites frontend/app/data/cluster_impressions.json
    (preserving existing impressions where bottle overlap >= 75%).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx
import numpy as np
from sklearn.cluster import DBSCAN

# Add frontend to path for imports
_ROOT = Path(__file__).resolve().parent.parent
_FRONTEND = _ROOT / "frontend"
sys.path.insert(0, str(_FRONTEND))

from app.services.flavor_map_2d_builder import (
    _ALL_DIMS,
    _UMAP_PARAMS,
    _build_feature_matrix,
)

IMPRESSIONS_FILE = _FRONTEND / "app" / "data" / "cluster_impressions.json"


def fetch_bottles(backend_url: str) -> list[dict]:
    """Fetch bottles with flavor profiles from backend."""
    resp = httpx.get(f"{backend_url}/api/bottles", params={"limit": 200}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    bottles = data["items"] if isinstance(data, dict) and "items" in data else data
    return [b for b in bottles if b.get("flavor_profile")]


def run_umap(feature_matrix: np.ndarray) -> np.ndarray:
    """Fit UMAP and return 2D embedding."""
    import umap

    n_neighbors = min(10, len(feature_matrix) - 1)
    params = {**_UMAP_PARAMS, "n_neighbors": n_neighbors}
    reducer = umap.UMAP(**params)
    return reducer.fit_transform(feature_matrix)


def run_dbscan(
    embedding: np.ndarray,
    eps: float,
    min_samples: int,
) -> np.ndarray:
    """Run DBSCAN and return labels."""
    db = DBSCAN(eps=eps, min_samples=min_samples)
    return db.fit_predict(embedding)


def load_existing_impressions() -> dict | None:
    """Load existing impressions file if present."""
    if IMPRESSIONS_FILE.exists():
        return json.loads(IMPRESSIONS_FILE.read_text())
    return None


def match_existing_impression(
    cluster_bottles: frozenset,
    existing: dict,
) -> str | None:
    """Find matching impression from existing file (75% overlap)."""
    if not existing:
        return None
    for _cid, comp in existing.get("clusters", {}).items():
        known = frozenset(
            (b[0], b[1]) for b in comp.get("bottles", [])
        )
        overlap = len(cluster_bottles & known) / max(len(known), 1)
        if overlap >= 0.75:
            return comp.get("impression")
    return None


def match_existing_outlier(
    brand: str,
    label: str | None,
    existing: dict,
) -> str | None:
    """Find matching outlier impression from existing file."""
    if not existing:
        return None
    key = f"{brand}__{label}" if label else brand
    outlier = existing.get("outliers", {}).get(key)
    if outlier:
        return outlier.get("impression")
    return None


def build_output(
    bottles: list[dict],
    labels: np.ndarray,
    eps: float,
    min_samples: int,
    existing: dict | None,
) -> dict:
    """Build the output JSON structure."""
    # Group by cluster
    clusters: dict[int, list[dict]] = {}
    noise: list[dict] = []
    for i, bottle in enumerate(bottles):
        cid = int(labels[i])
        if cid == -1:
            noise.append(bottle)
        else:
            clusters.setdefault(cid, []).append(bottle)

    output = {
        "_meta": {
            "description": "Pre-written cluster impressions for the 2D flavor map (UMAP + DBSCAN).",
            "generated_with": "scripts/calibrate_clusters.py",
            "umap_random_state": 42,
            "dbscan_eps": eps,
            "dbscan_min_samples": min_samples,
            "note": "Regenerate after adding/removing bottles. Auto-generation kicks in for unmatched clusters.",
        },
        "clusters": {},
        "outliers": {},
    }

    for cid in sorted(clusters):
        cluster_bottles = clusters[cid]
        bottle_keys = frozenset(
            (b["brand"], b.get("label") or None) for b in cluster_bottles
        )
        bottle_list = [[b["brand"], b.get("label") or None] for b in cluster_bottles]

        # Try to preserve existing impression
        impression = match_existing_impression(bottle_keys, existing)
        if not impression:
            # Generate placeholder from top-3 flavors
            profile_mean = {}
            for dim in _ALL_DIMS:
                vals = [b.get("flavor_profile", {}).get(dim, 0) for b in cluster_bottles]
                profile_mean[dim] = sum(vals) / len(vals)
            top3 = sorted(profile_mean.items(), key=lambda x: x[1], reverse=True)[:3]
            title = f"{top3[0][0].capitalize()}-leaning" if top3 else "Unnamed"
            impression = (
                f"{title} · TODO: Write impression. "
                f"Top notes: {', '.join(d for d, _ in top3)}."
            )

        output["clusters"][str(cid)] = {
            "bottles": bottle_list,
            "impression": impression,
        }

    for bottle in noise:
        brand = bottle["brand"]
        label = bottle.get("label") or None
        key = f"{brand}__{label}" if label else brand

        impression = match_existing_outlier(brand, label, existing)
        if not impression:
            profile = bottle.get("flavor_profile", {})
            top3 = sorted(profile.items(), key=lambda x: x[1], reverse=True)[:3]
            title = f"{top3[0][0].capitalize()}-leaning" if top3 else "Unnamed"
            impression = (
                f"{title} · TODO: Write impression. "
                f"Top notes: {', '.join(d for d, _ in top3)}."
            )

        output["outliers"][key] = {
            "label": label,
            "impression": impression,
        }

    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backend-url",
        default="http://localhost:8080",
        help="Backend API URL (default: http://localhost:8080)",
    )
    parser.add_argument("--eps", type=float, default=0.6, help="DBSCAN eps (default: 0.6)")
    parser.add_argument("--min-samples", type=int, default=2, help="DBSCAN min_samples (default: 2)")
    parser.add_argument("--write", action="store_true", help="Write output to impressions file")
    args = parser.parse_args()

    print(f"Fetching bottles from {args.backend_url}...", file=sys.stderr)
    bottles = fetch_bottles(args.backend_url)
    print(f"  {len(bottles)} bottles with flavor profiles", file=sys.stderr)

    print("Running UMAP...", file=sys.stderr)
    feature_matrix = _build_feature_matrix(bottles)
    embedding = run_umap(feature_matrix)

    x_range = embedding[:, 0].max() - embedding[:, 0].min()
    y_range = embedding[:, 1].max() - embedding[:, 1].min()
    print(f"  Coordinate range: x={x_range:.2f}, y={y_range:.2f}", file=sys.stderr)

    print(f"Running DBSCAN (eps={args.eps}, min_samples={args.min_samples})...", file=sys.stderr)
    labels = run_dbscan(embedding, args.eps, args.min_samples)

    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise = int((labels == -1).sum())
    print(f"  {n_clusters} clusters, {n_noise} noise points", file=sys.stderr)

    # Print cluster summary
    print("\n--- Cluster Summary ---", file=sys.stderr)
    for cid in sorted(set(labels)):
        if cid == -1:
            continue
        members = [bottles[i] for i, l in enumerate(labels) if l == cid]
        names = [f"{b['brand']} {b.get('label') or ''}".strip() for b in members]
        print(f"  Cluster {cid} ({len(members)}): {', '.join(names)}", file=sys.stderr)

    if n_noise:
        noise_bottles = [bottles[i] for i, l in enumerate(labels) if l == -1]
        names = [f"{b['brand']} {b.get('label') or ''}".strip() for b in noise_bottles]
        print(f"  Outliers ({n_noise}): {', '.join(names)}", file=sys.stderr)

    # Build output, preserving existing impressions where possible
    existing = load_existing_impressions()
    output = build_output(bottles, labels, args.eps, args.min_samples, existing)

    if args.write:
        IMPRESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        IMPRESSIONS_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
        print(f"\nWritten to {IMPRESSIONS_FILE}", file=sys.stderr)
    else:
        print(json.dumps(output, indent=2, ensure_ascii=False))
        print(f"\n(Use --write to save to {IMPRESSIONS_FILE})", file=sys.stderr)


if __name__ == "__main__":
    main()
