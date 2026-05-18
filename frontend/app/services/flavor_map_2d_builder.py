"""Build interactive 2D flavor map using UMAP + Plotly.

Computes a 2D projection of 16-dimensional flavor profiles via UMAP,
prepares a Plotly scatter figure with interactive features (hover, click,
color toggle), and serializes as JSON for client-side rendering via Plotly.js.

This module is the only part of the project that uses JavaScript libraries
(Plotly.js via CDN). This is a deliberate exception justified by the complexity
of interactive scatter plots — standard SVG + CSS cannot support zoom/pan/click
and dual-coloring modes simultaneously without significant client-side logic.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import plotly.graph_objects as go
from plotly import colors as px_colors
from sklearn.cluster import DBSCAN

logger = logging.getLogger(__name__)

# Flavor dimensions (mirrored from flavor_matrix_builder.py)
_GUSTATIVE_DIMS = [
    "sweet", "bitter", "sour", "citrusy", "fruity", "herbal",
    "floral", "spicy", "smoky", "vanilla", "woody", "minty",
    "earthy", "umami",
]
_STRUCTURAL_DIMS = ["body", "intensity"]
_ALL_DIMS = _GUSTATIVE_DIMS + _STRUCTURAL_DIMS

# UMAP hyperparameters (deterministic with random_state=42)
_UMAP_PARAMS = {
    "n_neighbors": None,  # Computed per dataset
    "min_dist": 0.3,
    "n_components": 2,
    "metric": "euclidean",
    "random_state": 42,
}

# Family colors (14 families in current collection)
_FAMILY_COLOR_MAP = {
    "Whiskey": "#92400e",
    "Gin": "#065f46",
    "Rum": "#7c2d12",
    "Vodka": "#e5e7eb",
    "Agave Spirit": "#713f12",
    "Brandy": "#78350f",
    "Wine-Based Aperitif": "#4c1d95",
    "Wine": "#831843",
    "Bitter Italiano": "#7f1d1d",
    "Aromatic Bitters": "#422006",
    "Amaro": "#1e3a5f",
    "Liqueur": "#134e4a",
    "Sake & Umeshu": "#f0fdf4",
    "Misc": "#6b7280",
}

# Cluster colors (Plotly qualitative palette, 10 colors)
_CLUSTER_COLORS = px_colors.qualitative.Set2


# ---------------------------------------------------------------------------
# Data container
# ---------------------------------------------------------------------------

@dataclass
class FlavorMap2DData:
    """Result of 2D flavor map computation."""
    plotly_json: str = ""  # Serialized Plotly figure
    cluster_impressions: dict[int, str] = field(default_factory=dict)
    cluster_sizes: dict[int, int] = field(default_factory=dict)
    n_clusters: int = 0
    umap_params: dict = field(default_factory=dict)
    generation_time: str = ""


# DBSCAN on 2D UMAP embedding (visual clustering)
_DBSCAN_EPS = 0.6
_DBSCAN_MIN_SAMPLES = 2


# ---------------------------------------------------------------------------
# Impression loading & generation
# ---------------------------------------------------------------------------

_IMPRESSIONS_FILE = Path(__file__).resolve().parent.parent / "data" / "cluster_impressions.json"


def _load_impressions() -> tuple[dict[int, dict], dict[tuple[str, str | None], str]]:
    """Load cluster and outlier impressions from external JSON file.
    
    Returns:
        (cluster_compositions, noise_impressions) where:
        - cluster_compositions: {cluster_id → {"bottles": frozenset, "impression": str}}
        - noise_impressions: {(brand, label) → impression_str}
    """
    if not _IMPRESSIONS_FILE.exists():
        logger.warning("Impressions file not found: %s", _IMPRESSIONS_FILE)
        return {}, {}
    
    raw = json.loads(_IMPRESSIONS_FILE.read_text())
    
    clusters = {}
    for cid_str, comp in raw.get("clusters", {}).items():
        clusters[int(cid_str)] = {
            "bottles": frozenset(
                (b[0], b[1]) for b in comp.get("bottles", [])
            ),
            "impression": comp.get("impression", ""),
        }
    
    outliers = {}
    for _key, data in raw.get("outliers", {}).items():
        # Parse key: "Brand__Label" or "Brand" (no label)
        brand = _key.split("__")[0]
        label = data.get("label")
        outliers[(brand, label)] = data.get("impression", "")
    
    logger.debug("Loaded %d cluster impressions, %d outlier impressions", len(clusters), len(outliers))
    return clusters, outliers


# Loaded at module import time (cached for process lifetime)
CLUSTER_COMPOSITIONS, NOISE_IMPRESSIONS = _load_impressions()


def _auto_impression(bottles_in_cluster: list[dict]) -> str:
    """Auto-generate impression from top-3 flavor dimensions."""
    if not bottles_in_cluster:
        return "Empty cluster."
    
    # Aggregate mean profile
    profile_mean = {}
    for dim in _ALL_DIMS:
        values = [b.get("flavor_profile", {}).get(dim, 0) for b in bottles_in_cluster]
        profile_mean[dim] = sum(values) / len(values)
    
    # Top 3 dimensions by mean value
    top3 = sorted(profile_mean.items(), key=lambda x: x[1], reverse=True)[:3]
    parts = [f"{dim} ({val:.1f})" for dim, val in top3 if val > 0.1]
    
    if not parts:
        return "Unique profile · No dominant flavor dimensions."
    
    return f"Signature notes: {', '.join(parts)}."


def get_cluster_impression(
    cluster_id: int,
    bottles_in_cluster: list[dict],
) -> str:
    """Match cluster to pre-written impression by bottle identity.
    
    For real clusters (id >= 0): matches against CLUSTER_COMPOSITIONS
    using 75% overlap threshold.
    For noise (id < 0): should not be called (use get_noise_impression).
    Falls back to auto-generate for unmatched clusters.
    """
    # Build identity key for this cluster
    cluster_key = frozenset(
        (b.get("brand", "Unknown"), b.get("label") or None)
        for b in bottles_in_cluster
    )
    
    # Find best-matching composition (≥75% overlap)
    best_overlap = 0.0
    best_impression = None
    for _cid, comp in CLUSTER_COMPOSITIONS.items():
        known_key = comp["bottles"]
        overlap = len(cluster_key & known_key) / max(len(known_key), 1)
        if overlap > best_overlap:
            best_overlap = overlap
            best_impression = comp["impression"]
    
    if best_overlap >= 0.75 and best_impression:
        return best_impression
    
    # Auto-generate for unmatched
    return _auto_impression(bottles_in_cluster)


def get_noise_impression(bottle: dict) -> str:
    """Get per-bottle impression for a DBSCAN noise point (outlier)."""
    key = (bottle.get("brand", "Unknown"), bottle.get("label") or None)
    if key in NOISE_IMPRESSIONS:
        return NOISE_IMPRESSIONS[key]
    return _auto_impression([bottle])


# ---------------------------------------------------------------------------
# UMAP projection
# ---------------------------------------------------------------------------

def _build_feature_matrix(bottles: list[dict]) -> np.ndarray:
    """Convert flavor profiles to N×16 feature matrix."""
    matrix = []
    for bottle in bottles:
        profile = bottle.get("flavor_profile", {})
        row = [profile.get(dim, 0) for dim in _ALL_DIMS]
        matrix.append(row)
    return np.array(matrix, dtype=float)


def _fit_umap(feature_matrix: np.ndarray) -> np.ndarray:
    """Fit UMAP and return 2D embedding."""
    try:
        import umap
    except ImportError:
        raise ImportError("umap-learn not installed")
    
    n_neighbors = min(10, len(feature_matrix) - 1)
    params = {
        **_UMAP_PARAMS,
        "n_neighbors": n_neighbors,
    }
    
    logger.debug(f"UMAP params: {params}")
    
    reducer = umap.UMAP(**params)
    embedding = reducer.fit_transform(feature_matrix)
    
    logger.info(f"UMAP projection: {len(feature_matrix)} bottles → {embedding.shape}")
    return embedding


def _cluster_dbscan(
    embedding: np.ndarray,
    bottles: list[dict],
) -> dict[int, int]:
    """Run DBSCAN on 2D UMAP embedding. Returns {bottle_id → cluster_id}.
    
    Noise points (label -1) are kept as cluster_id = -1.
    """
    db = DBSCAN(eps=_DBSCAN_EPS, min_samples=_DBSCAN_MIN_SAMPLES)
    labels = db.fit_predict(embedding)
    
    assignments = {}
    for i, bottle in enumerate(bottles):
        assignments[bottle["id"]] = int(labels[i])
    
    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise = int((labels == -1).sum())
    logger.info(
        "DBSCAN: eps=%.2f min_samples=%d → %d clusters, %d noise points",
        _DBSCAN_EPS, _DBSCAN_MIN_SAMPLES, n_clusters, n_noise,
    )
    return assignments


# ---------------------------------------------------------------------------
# Plotly figure building
# ---------------------------------------------------------------------------

def _build_plotly_figure(
    bottles: list[dict],
    embedding: np.ndarray,
    cluster_assignments: dict[int, int],
    cluster_impressions: dict[int, str],
) -> str:
    """Build Plotly scatter figure and return as JSON string.
    
    Args:
        bottles: List of bottle dicts
        embedding: N×2 UMAP projection
        cluster_assignments: {bottle_id → cluster_id}
        cluster_impressions: {cluster_id → impression_text}
    
    Returns:
        JSON string of Plotly figure (with dual color arrays in layout.meta)
    """
    n = len(bottles)
    
    # Prepare per-point data
    cluster_colors = []
    family_colors = []
    labels = []
    customdata = []
    
    for bottle in bottles:
        bottle_id = bottle["id"]
        cluster_id = cluster_assignments.get(bottle_id, -1)
        
        # Colors (noise = grey)
        if cluster_id < 0:
            cluster_color = "#9ca3af"  # grey-400 for outliers
        else:
            cluster_color = _CLUSTER_COLORS[cluster_id % len(_CLUSTER_COLORS)]
        family_color = _FAMILY_COLOR_MAP.get(bottle.get("family_name", "Misc"), "#6b7280")
        cluster_colors.append(cluster_color)
        family_colors.append(family_color)
        
        # Label
        label_text = bottle.get("brand", "Unknown")
        if bottle.get("label"):
            label_text += " " + bottle["label"]
        labels.append(label_text)
        
        # Top 3 flavor dimensions for hover preview
        profile = bottle.get("flavor_profile", {})
        top3 = sorted(
            [(dim, profile.get(dim, 0)) for dim in _ALL_DIMS],
            key=lambda x: x[1],
            reverse=True
        )[:3]
        top3_str = " · ".join(f"{d}: {v}" for d, v in top3 if v > 0.1)
        
        # Customdata: [id, brand, label, class_name, family, top3_str, cluster_id, impression, on_hand, full_profile_json, cluster_display]
        full_profile_json = json.dumps(profile)
        cluster_display = "Outlier" if cluster_id < 0 else f"Cluster {cluster_id + 1}"
        customdata.append([
            bottle_id,
            bottle.get("brand", "Unknown"),
            bottle.get("label", ""),
            bottle.get("class_name", "Unknown"),
            bottle.get("family_name", "Misc"),
            top3_str,
            cluster_id,
            cluster_impressions.get(cluster_id, ""),
            1 if bottle.get("on_hand") else 0,
            full_profile_json,
            cluster_display,
        ])
    
    # Hover template
    hovertemplate = (
        "<b>%{text}</b><br>"
        "<i>%{customdata[3]}</i> · %{customdata[4]}<br>"
        "%{customdata[10]}<br>"
        "<br>"
        "Top notes: %{customdata[5]}<br>"
        "<extra></extra>"
    )
    
    # Create figure
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=embedding[:, 0].tolist(),
        y=embedding[:, 1].tolist(),
        mode="markers+text",
        text=labels,
        textposition="top center",
        textfont=dict(size=9, color="#475569"),  # slate-600
        marker=dict(
            size=12,
            color=cluster_colors,  # Default coloring
            opacity=0.85,
            line=dict(width=1, color="white"),
        ),
        hovertemplate=hovertemplate,
        customdata=customdata,
        name="bottles",
    ))
    
    fig.update_layout(
        plot_bgcolor="#f8fafc",  # slate-50
        paper_bgcolor="#f8fafc",
        xaxis=dict(
            showgrid=False,
            zeroline=False,
            showticklabels=False,
            title="",
        ),
        yaxis=dict(
            showgrid=False,
            zeroline=False,
            showticklabels=False,
            title="",
        ),
        margin=dict(l=20, r=20, t=40, b=20),
        showlegend=False,
        title=dict(
            text="Flavor Space · 2D projection (UMAP)",
            font=dict(size=14, color="#1e293b"),  # slate-800
            x=0.5,
        ),
        hoverlabel=dict(
            bgcolor="white",
            bordercolor="#94a3b8",
            font_size=12,
            font_color="#1e293b",
            font_family="Inter",
        ),
        dragmode="pan",
    )
    
    # Embed both color arrays in layout.meta for JS toggle
    fig.update_layout(meta={
        "cluster_colors": cluster_colors,
        "family_colors": family_colors,
    })
    
    # Serialize as plain JSON with Python lists (not binary bdata format)
    # so Plotly.js can consume it directly via Plotly.newPlot()
    from plotly.utils import PlotlyJSONEncoder
    return json.dumps(fig.to_dict(), cls=PlotlyJSONEncoder)


# ---------------------------------------------------------------------------
# Public builder
# ---------------------------------------------------------------------------

def build_flavor_map_2d(
    bottles: list[dict],
    cluster_assignments: dict[int, int] | None = None,
) -> FlavorMap2DData:
    """Build 2D flavor map with UMAP projection and interactive Plotly figure.
    
    Clustering is done via DBSCAN on the 2D UMAP embedding (visual clusters).
    The cluster_assignments parameter (from heatmap) is ignored.
    
    Args:
        bottles: List of bottle dicts with flavor_profile, brand, label, etc.
        cluster_assignments: Ignored (kept for API compat). DBSCAN used instead.
    
    Returns:
        FlavorMap2DData with plotly_json, cluster_impressions, generation_time
    
    Raises:
        ImportError: If umap-learn not installed
        ValueError: If bottles list is too small
    """
    t0 = datetime.now(timezone.utc)
    
    # Filter to bottles with flavor profiles
    bottles_with_profile = [b for b in bottles if b.get("flavor_profile")]
    
    if len(bottles_with_profile) < 2:
        raise ValueError("Need at least 2 bottles with flavor profiles")
    
    # Build feature matrix & fit UMAP
    feature_matrix = _build_feature_matrix(bottles_with_profile)
    embedding = _fit_umap(feature_matrix)
    
    # Cluster on 2D embedding via DBSCAN
    dbscan_assignments = _cluster_dbscan(embedding, bottles_with_profile)
    
    # Split noise into individual outlier IDs (-1, -2, -3, ...)
    # so each outlier gets its own panel card and impression.
    noise_counter = 0
    for bottle in bottles_with_profile:
        if dbscan_assignments.get(bottle["id"], -1) == -1:
            noise_counter += 1
            dbscan_assignments[bottle["id"]] = -noise_counter  # -1, -2, -3...
    
    # Build cluster-to-bottles mapping
    cluster_id_to_bottles: dict[int, list[dict]] = {}
    for bottle in bottles_with_profile:
        cid = dbscan_assignments.get(bottle["id"], -1)
        if cid not in cluster_id_to_bottles:
            cluster_id_to_bottles[cid] = []
        cluster_id_to_bottles[cid].append(bottle)
    
    # Log cluster composition for debugging / verification
    for cid in sorted(cluster_id_to_bottles, key=lambda x: (x < 0, abs(x))):
        cbs = cluster_id_to_bottles[cid]
        names = ", ".join(
            f"{b['brand']} {b.get('label') or ''}".strip() for b in cbs
        )
        label = f"Cluster {cid}" if cid >= 0 else f"Outlier ({names})"
        logger.info("%s (%d bottles): %s", label, len(cbs), names)
    
    # Build impressions: clusters via composition match, outliers per-bottle
    cluster_impressions = {}
    cluster_sizes = {}
    for cid, cluster_bottles in cluster_id_to_bottles.items():
        if cid >= 0:
            cluster_impressions[cid] = get_cluster_impression(cid, cluster_bottles)
        else:
            # Single-bottle outlier
            cluster_impressions[cid] = get_noise_impression(cluster_bottles[0])
        cluster_sizes[cid] = len(cluster_bottles)
    
    # Build Plotly figure
    plotly_json = _build_plotly_figure(
        bottles_with_profile,
        embedding,
        dbscan_assignments,
        cluster_impressions,
    )
    
    t1 = datetime.now(timezone.utc)
    generation_time = f"{(t1 - t0).total_seconds():.2f}s"
    
    return FlavorMap2DData(
        plotly_json=plotly_json,
        cluster_impressions=cluster_impressions,
        cluster_sizes=cluster_sizes,
        n_clusters=len([k for k in cluster_id_to_bottles if k >= 0]),
        umap_params={
            "n_neighbors": min(10, len(bottles_with_profile) - 1),
            "min_dist": _UMAP_PARAMS["min_dist"],
            "metric": _UMAP_PARAMS["metric"],
            "dbscan_eps": _DBSCAN_EPS,
            "dbscan_min_samples": _DBSCAN_MIN_SAMPLES,
        },
        generation_time=generation_time,
    )
