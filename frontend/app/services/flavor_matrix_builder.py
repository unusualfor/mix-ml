"""Compute pairwise flavor-distance matrix with hierarchical clustering.

The distance metric intentionally duplicates the backend's
``app.services.flavor.flavor_distance`` (~15 lines).  This avoids coupling
the frontend package to internal backend modules.  If the metric changes in
the backend, propagate the change here manually.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
from scipy.cluster.hierarchy import fcluster, leaves_list, linkage
from scipy.spatial.distance import squareform

# ---------------------------------------------------------------------------
# Flavor-distance metric (mirrors backend app.services.flavor)
# ---------------------------------------------------------------------------

_GUSTATIVE_DIMS = [
    "sweet", "bitter", "sour", "citrusy", "fruity", "herbal",
    "floral", "spicy", "smoky", "vanilla", "woody", "minty",
    "earthy", "umami",
]
_STRUCTURAL_DIMS = ["body", "intensity"]
_MAX_VAL = 5
_GUSTATIVE_NORM = math.sqrt(len(_GUSTATIVE_DIMS) * _MAX_VAL ** 2)
_STRUCTURAL_NORM = math.sqrt(len(_STRUCTURAL_DIMS) * _MAX_VAL ** 2)


def _clamp(v: int) -> int:
    return max(0, min(_MAX_VAL, v))


def _euclidean(a: dict, b: dict, dims: list[str], norm: float) -> float:
    sq = sum((_clamp(a.get(k, 0)) - _clamp(b.get(k, 0))) ** 2 for k in dims)
    return math.sqrt(sq) / norm


def flavor_distance(pa: dict, pb: dict) -> float:
    """Weighted Euclidean distance in [0, 1].  0 = identical, 1 = max."""
    dg = _euclidean(pa, pb, _GUSTATIVE_DIMS, _GUSTATIVE_NORM)
    ds = _euclidean(pa, pb, _STRUCTURAL_DIMS, _STRUCTURAL_NORM)
    return 0.7 * dg + 0.3 * ds


# ---------------------------------------------------------------------------
# Data container
# ---------------------------------------------------------------------------

@dataclass
class FlavorMatrixData:
    ordered_bottles: list[dict] = field(default_factory=list)
    distance_matrix: list[list[float]] = field(default_factory=list)
    clusters: list[dict] = field(default_factory=list)
    singleton_bottle_ids: list[int] = field(default_factory=list)
    inter_cluster_pairs: list[dict] = field(default_factory=list)
    generation_time: str = ""


# ---------------------------------------------------------------------------
# Public builder
# ---------------------------------------------------------------------------

CLUSTER_THRESHOLD = 0.25
INTER_CLUSTER_TOP_N = 5


def build_flavor_matrix(
    bottles: list[dict],
    *,
    cluster_threshold: float = CLUSTER_THRESHOLD,
) -> FlavorMatrixData:
    """Compute pairwise distances, hierarchical clustering, and ordering."""
    # Filter to bottles with a flavor profile
    bottles = [b for b in bottles if b.get("flavor_profile")]
    n = len(bottles)

    if n == 0:
        return FlavorMatrixData(generation_time=_now())

    # Pairwise distance matrix
    mat = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            d = flavor_distance(
                bottles[i]["flavor_profile"],
                bottles[j]["flavor_profile"],
            )
            mat[i, j] = d
            mat[j, i] = d

    # Hierarchical clustering & leaf ordering
    if n > 1:
        condensed = squareform(mat, checks=False)
        Z = linkage(condensed, method="average")
        order = list(leaves_list(Z))
        cluster_labels = list(fcluster(Z, t=cluster_threshold, criterion="distance"))
    else:
        order = [0]
        cluster_labels = [1]

    # Reorder matrix and bottles
    reordered_mat = mat[np.ix_(order, order)]
    ordered_bottles = [bottles[i] for i in order]
    # Map original indices → cluster label
    orig_to_cluster = {i: cluster_labels[i] for i in range(n)}
    # Build ordered cluster label list
    ordered_cluster_labels = [orig_to_cluster[i] for i in order]

    # Group into clusters
    cluster_groups: dict[int, list[int]] = {}
    for ordered_idx, orig_idx in enumerate(order):
        cid = orig_to_cluster[orig_idx]
        cluster_groups.setdefault(cid, []).append(ordered_idx)

    clusters: list[dict] = []
    singleton_ids: list[int] = []
    for cid in sorted(cluster_groups, key=lambda c: -len(cluster_groups[c])):
        members = cluster_groups[cid]
        member_bottles = [ordered_bottles[m] for m in members]
        if len(members) == 1:
            singleton_ids.append(member_bottles[0]["id"])
            continue
        # Mean internal distance
        dists = [
            reordered_mat[i, j]
            for ii, i in enumerate(members)
            for j in members[ii + 1:]
        ]
        mean_d = sum(dists) / len(dists) if dists else 0.0
        clusters.append({
            "idx": len(clusters) + 1,
            "bottle_ids": [b["id"] for b in member_bottles],
            "bottles": member_bottles,
            "count": len(members),
            "mean_distance": round(mean_d, 3),
        })

    # Inter-cluster nearest pairs
    pairs: list[tuple[float, int, int]] = []
    for i in range(n):
        for j in range(i + 1, n):
            oi, oj = order[i], order[j]  # noqa: E741
            # i,j are ordered indices; use ordered_cluster_labels
            if ordered_cluster_labels[i] != ordered_cluster_labels[j]:
                pairs.append((reordered_mat[i, j], i, j))
    pairs.sort()

    inter_pairs = []
    for d, i, j in pairs[:INTER_CLUSTER_TOP_N]:
        bi, bj = ordered_bottles[i], ordered_bottles[j]
        inter_pairs.append({
            "bottle_a": bi,
            "bottle_b": bj,
            "distance": round(d, 3),
        })

    return FlavorMatrixData(
        ordered_bottles=ordered_bottles,
        distance_matrix=reordered_mat.tolist(),
        clusters=clusters,
        singleton_bottle_ids=singleton_ids,
        inter_cluster_pairs=inter_pairs,
        generation_time=_now(),
    )


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
