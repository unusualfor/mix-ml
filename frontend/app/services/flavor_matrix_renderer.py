"""Render the flavor-distance heatmap as a plain SVG string.

No external chart libraries — just string concatenation producing valid SVG.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

from app.services.flavor_matrix_builder import FlavorMatrixData

# ---------------------------------------------------------------------------
# Viridis-inspired colour ramp (5 steps)
# ---------------------------------------------------------------------------

_COLOR_STEPS: list[tuple[float, str]] = [
    (0.10, "#440154"),   # purple  — very similar
    (0.20, "#3b528b"),
    (0.30, "#21908d"),
    (0.40, "#5dc863"),
    (999.0, "#fde725"),  # yellow  — very different
]

_SELF_COLOR = "#1e293b"  # slate-800 for diagonal


def viridis_color(distance: float) -> str:
    """Map a distance value to a viridis-inspired hex colour."""
    for threshold, color in _COLOR_STEPS:
        if distance <= threshold:
            return color
    return _COLOR_STEPS[-1][1]


# ---------------------------------------------------------------------------
# SVG generation
# ---------------------------------------------------------------------------

_CELL = 22
_LABEL_MARGIN = 220
_TOP_MARGIN = 10
_BOTTOM_LABEL_MARGIN = 200
_RIGHT_MARGIN = 120  # space for rotated bottom-right labels extending right
_TRUNC = 32


def _trunc(s: str) -> str:
    return s if len(s) <= _TRUNC else s[: _TRUNC - 1] + "\u2026"


def _display_name(b: dict) -> str:
    parts = [b.get("brand", "")]
    if b.get("label"):
        parts.append(b["label"])
    return " ".join(parts)


def render_flavor_matrix_svg(data: FlavorMatrixData) -> str:
    """Return a complete SVG string for the heatmap."""
    bottles = data.ordered_bottles
    matrix = data.distance_matrix
    n = len(bottles)

    if n == 0:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="100"><text x="200" y="50" text-anchor="middle" fill="#64748b" font-size="14">No bottles with flavor profiles.</text></svg>'

    grid_w = n * _CELL
    grid_h = n * _CELL
    svg_w = _LABEL_MARGIN + grid_w + _RIGHT_MARGIN
    svg_h = _TOP_MARGIN + grid_h + _BOTTOM_LABEL_MARGIN

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="100%" viewBox="0 0 {svg_w} {svg_h}" '
        f'style="max-width:{svg_w}px">'
    )
    parts.append(
        '<style>text{font-family:Inter,system-ui,sans-serif}'
        ' a text{fill:#334155} a:hover text{fill:#b45309}</style>'
    )

    # Row labels (left side)
    parts.append(f'<g transform="translate({_LABEL_MARGIN - 8}, {_TOP_MARGIN})">')
    for i, b in enumerate(bottles):
        y = i * _CELL + _CELL * 0.65
        name = escape(_trunc(_display_name(b)))
        bid = b.get("id", "")
        parts.append(
            f'<a xlink:href="/inventory#bottle-{bid}">'
            f'<text x="0" y="{y}" text-anchor="end" font-size="11" fill="#334155">'
            f'{name}</text></a>'
        )
    parts.append("</g>")

    # Column labels (bottom, rotated)
    parts.append(f'<g transform="translate({_LABEL_MARGIN}, {_TOP_MARGIN + grid_h + 8})">')
    for i, b in enumerate(bottles):
        x = i * _CELL + _CELL * 0.5
        name = escape(_trunc(_display_name(b)))
        bid = b.get("id", "")
        parts.append(
            f'<a xlink:href="/inventory#bottle-{bid}">'
            f'<text x="{x}" y="0" text-anchor="start" font-size="11" fill="#334155" '
            f'transform="rotate(50, {x}, 0)">'
            f'{name}</text></a>'
        )
    parts.append("</g>")

    # Cells
    parts.append(f'<g transform="translate({_LABEL_MARGIN}, {_TOP_MARGIN})">')
    for i in range(n):
        for j in range(n):
            x = j * _CELL
            y = i * _CELL
            d = matrix[i][j]
            if i == j:
                color = _SELF_COLOR
            else:
                color = viridis_color(d)
            ni = escape(_display_name(bottles[i]))
            nj = escape(_display_name(bottles[j]))
            parts.append(
                f'<rect x="{x}" y="{y}" width="{_CELL}" height="{_CELL}" '
                f'fill="{color}" stroke="#fff" stroke-width="0.5">'
                f'<title>{ni} \u00d7 {nj} = {d:.3f}</title></rect>'
            )
    parts.append("</g>")

    parts.append("</svg>")
    return "\n".join(parts)
