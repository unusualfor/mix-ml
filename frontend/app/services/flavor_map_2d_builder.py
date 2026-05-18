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


# ---------------------------------------------------------------------------
# Impression loading & generation
# ---------------------------------------------------------------------------

# Pre-written impressions keyed by frozenset of (brand, label) tuples.
# Matched against actual UMAP output (random_state=42).
CLUSTER_IMPRESSIONS_BY_BOTTLES = {
    frozenset([
        ("Formidabile", None),
        ("Montenegro", None),
        ("Nonino", "Quintessentia"),
        ("Aperol", None),
        ("A. Smith Bowman", "John J. Bowman Single Barrel"),
        ("Buffalo Trace", "Eagle Rare 10 Year"),
        ("Buffalo Trace", "Kentucky Straight Bourbon"),
        ("Buffalo Trace", "Blanton's Original Single Barrel"),
        ("Buffalo Trace", "Elmer T. Lee Single Barrel Sour Mash"),
        ("Buffalo Trace", "Barrel Select Sazerac"),
        ("Buffalo Trace", "Colonel E.H. Taylor Small Batch"),
        ("Calumet Farm", "Vintage Release 8 Years"),
        ("Metaxa", "3 Stars"),
        ("Tintura Imperiale", None),
        ("Godo Shusei", "Oshuku Umeshu (Ohshukubai Shigoku Nidan)"),
        ("Carpano", "Antica Formula"),
        ("Martini", "Riserva Speciale Rubino"),
        ("Mt Defiance", "Sweet Vermouth"),
        ("Buffalo Trace", "Weller Special Reserve Single Barrel Select"),
        ("Buffalo Trace", "Weller 12 Year"),
        ("Maker's Mark", "101 Proof"),
        ("Ragged Branch", "Wheated Bourbon"),
    ]):
        "Warming & structured · Vanilla, oak and body dominate. "
        "Aged American whiskeys anchor the group, but Carpano Antica and "
        "Mt Defiance Sweet Vermouth earn their place — both share the same "
        "rich, slow character. Montenegro and Nonino bridge bitter and sweet "
        "in the same warm register. Outliers (Tintura, Umeshu) land here on "
        "sheer intensity and body.",

    frozenset([
        ("Angostura", "Aromatic Bitters"),
        ("Fusetti", "Bitter Mexico"),
        ("Fusetti", "Bitter Cacao"),
        ("Fusetti", "Bitter Original"),
        ("Fusetti", "Bitter Mare"),
        ("Fusetti", "Bitter Banana"),
        ("Campari", None),
        ("Carpano", "Punt e Mes"),
    ]):
        "Bitter italians · Dominant amaro and spice, anchored by citrus. "
        "The backbone of aperitivo culture — from Campari to Angostura, "
        "these define the Italian bitter hour.",

    frozenset([
        ("Komasa", "Komikan"),
        ("Suntory", "Roku"),
        ("Suntory", "Roku Sakura Edition"),
        ("Tanqueray", "No. Ten"),
        ("Pilla", "Select Aperitivo"),
        ("Martini", "Riserva Speciale Ambrato"),
        ("Martini", "Vermouth Rosso"),
    ]):
        "Aromatic & citrus-forward · Light-bodied, floral and herbaceous. "
        "Gin is the core, but Select Aperitivo and Martini Ambrato share "
        "enough botanical lift to cluster alongside. Martini Rosso drifts "
        "here on its herbal-citrus balance.",

    frozenset([
        ("Tatsuuma-Honke", "Hakushika"),
        ("Asahi Shuzo", "Dassai 45"),
    ]):
        "Delicate umami · Low intensity, subtle fruit, distinctive umami. "
        "Japanese sake occupies its own quiet corner — nothing else in the "
        "collection competes for this space.",

    frozenset([
        ("Koval", "Thresh & Winnow Foret"),
        ("D'Argo", "Chandolia Mastiha"),
    ]):
        "Resinous botanicals · Two bottles from different worlds — "
        "a Chicago forest gin and a Chios mastic liqueur — that share "
        "a rare quality: they taste like somewhere specific. "
        "Resinous, herb-heavy, with a mentholated edge.",

    frozenset([
        ("Braulio", "Riserva Speciale"),
        ("Cynar", None),
    ]):
        "Alpine & artichoke bitterness · Both reach deep into bitter-herbal "
        "territory — Braulio via mountain herbs, Cynar via artichoke. "
        "Interchangeable in some stirred cocktail contexts.",
}


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
    
    Falls back to auto-generate for unmatched clusters.
    Uses 75% overlap threshold for robustness against minor UMAP drift.
    """
    # Build identity key for this cluster
    cluster_key = frozenset(
        (b.get("brand", "Unknown"), b.get("label") or None)
        for b in bottles_in_cluster
    )
    
    # Exact match
    if cluster_key in CLUSTER_IMPRESSIONS_BY_BOTTLES:
        return CLUSTER_IMPRESSIONS_BY_BOTTLES[cluster_key]
    
    # Overlap match: find best-matching known impression (≥75% overlap)
    best_overlap = 0.0
    best_impression = None
    for known_key, impression in CLUSTER_IMPRESSIONS_BY_BOTTLES.items():
        overlap = len(cluster_key & known_key) / max(len(known_key), 1)
        if overlap > best_overlap:
            best_overlap = overlap
            best_impression = impression
    
    if best_overlap >= 0.75 and best_impression:
        return best_impression
    
    # Auto-generate for unmatched
    return _auto_impression(bottles_in_cluster)


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
        cluster_id = cluster_assignments.get(bottle_id, 0)
        
        # Colors
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
            cluster_id + 1,  # 1-indexed for display
        ])
    
    # Hover template
    hovertemplate = (
        "<b>%{text}</b><br>"
        "<i>%{customdata[3]}</i> · %{customdata[4]}<br>"
        "Cluster %{customdata[10]}<br>"
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
    cluster_assignments: dict[int, int],
) -> FlavorMap2DData:
    """Build 2D flavor map with UMAP projection and interactive Plotly figure.
    
    Args:
        bottles: List of bottle dicts with flavor_profile, brand, label, etc.
        cluster_assignments: {bottle_id → cluster_id} from FlavorMatrixData
    
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
    
    # Build cluster impressions
    cluster_id_to_bottles = {}
    for bottle in bottles_with_profile:
        cid = cluster_assignments.get(bottle["id"], 0)
        if cid not in cluster_id_to_bottles:
            cluster_id_to_bottles[cid] = []
        cluster_id_to_bottles[cid].append(bottle)
    
    # Log cluster composition for debugging / verification
    for cid in sorted(cluster_id_to_bottles):
        cbs = cluster_id_to_bottles[cid]
        names = ", ".join(
            f"{b['brand']} {b.get('label') or ''}".strip() for b in cbs
        )
        logger.info("Cluster %d (%d bottles): %s", cid, len(cbs), names)
    
    cluster_impressions = {}
    cluster_sizes = {}
    for cid, cluster_bottles in cluster_id_to_bottles.items():
        cluster_impressions[cid] = get_cluster_impression(cid, cluster_bottles)
        cluster_sizes[cid] = len(cluster_bottles)
    
    # Build Plotly figure
    plotly_json = _build_plotly_figure(
        bottles_with_profile,
        embedding,
        cluster_assignments,
        cluster_impressions,
    )
    
    t1 = datetime.now(timezone.utc)
    generation_time = f"{(t1 - t0).total_seconds():.2f}s"
    
    return FlavorMap2DData(
        plotly_json=plotly_json,
        cluster_impressions=cluster_impressions,
        cluster_sizes=cluster_sizes,
        n_clusters=len(cluster_id_to_bottles),
        umap_params={
            "n_neighbors": min(10, len(bottles_with_profile) - 1),
            "min_dist": _UMAP_PARAMS["min_dist"],
            "metric": _UMAP_PARAMS["metric"],
        },
        generation_time=generation_time,
    )
