"""Flavor-profile distance and aggregation utilities.

All functions are pure (no DB I/O).  The distance metric splits the
16-dimensional flavor space into a gustative sub-space (14 dims) and a
structural sub-space (2 dims), computes normalised Euclidean distances
for each, then returns a weighted combination.
"""

from __future__ import annotations

import math
import statistics
from typing import Literal

from pydantic import BaseModel


# -- dimension constants -----------------------------------------------------

DIMS_GUSTATIVE: list[str] = [
    "sweet", "bitter", "sour", "citrusy", "fruity", "herbal",
    "floral", "spicy", "smoky", "vanilla", "woody", "minty",
    "earthy", "umami",
]

DIMS_STRUCTURAL: list[str] = ["body", "intensity"]

_ALL_DIMS: set[str] = set(DIMS_GUSTATIVE) | set(DIMS_STRUCTURAL)

_MAX_VAL = 5
_GUSTATIVE_NORM = math.sqrt(len(DIMS_GUSTATIVE) * _MAX_VAL ** 2)
_STRUCTURAL_NORM = math.sqrt(len(DIMS_STRUCTURAL) * _MAX_VAL ** 2)


# -- Pydantic models --------------------------------------------------------

class PerDimensionDetail(BaseModel):
    dimension: str
    group: Literal["gustative", "structural"]
    value_a: int
    value_b: int
    abs_delta: int
    squared_contribution: float


class FlavorBreakdownResult(BaseModel):
    total_distance: float
    gustative_distance: float
    structural_distance: float
    weights: dict[str, float]
    per_dimension: list[PerDimensionDetail]


# -- internal helpers --------------------------------------------------------

def _validate_profile(profile: dict[str, int], label: str) -> None:
    keys = set(profile.keys())
    missing = _ALL_DIMS - keys
    if missing:
        raise ValueError(
            f"{label}: missing keys: {sorted(missing)}"
        )
    extra = keys - _ALL_DIMS
    if extra:
        raise ValueError(
            f"{label}: extra keys: {sorted(extra)}"
        )


def _validate_weights(gw: float, sw: float) -> None:
    if abs((gw + sw) - 1.0) > 1e-6:
        raise ValueError(
            f"gustative_weight + structural_weight must sum to 1 "
            f"(got {gw} + {sw} = {gw + sw})"
        )


def _clamp(v: int) -> int:
    return max(0, min(_MAX_VAL, v))


def _euclidean(
    a: dict[str, int],
    b: dict[str, int],
    dims: list[str],
    norm: float,
) -> float:
    sq_sum = sum((_clamp(a[k]) - _clamp(b[k])) ** 2 for k in dims)
    return math.sqrt(sq_sum) / norm


# -- public API --------------------------------------------------------------

def flavor_distance(
    profile_a: dict[str, int],
    profile_b: dict[str, int],
    *,
    gustative_weight: float = 0.7,
    structural_weight: float = 0.3,
) -> float:
    """Weighted Euclidean distance in [0, 1].  0 = identical, 1 = max."""
    _validate_profile(profile_a, "profile_a")
    _validate_profile(profile_b, "profile_b")
    _validate_weights(gustative_weight, structural_weight)

    d_g = _euclidean(profile_a, profile_b, DIMS_GUSTATIVE, _GUSTATIVE_NORM)
    d_s = _euclidean(profile_a, profile_b, DIMS_STRUCTURAL, _STRUCTURAL_NORM)
    return gustative_weight * d_g + structural_weight * d_s


def flavor_breakdown(
    profile_a: dict[str, int],
    profile_b: dict[str, int],
    *,
    gustative_weight: float = 0.7,
    structural_weight: float = 0.3,
) -> FlavorBreakdownResult:
    """Full decomposition of the distance for diagnostics."""
    _validate_profile(profile_a, "profile_a")
    _validate_profile(profile_b, "profile_b")
    _validate_weights(gustative_weight, structural_weight)

    d_g = _euclidean(profile_a, profile_b, DIMS_GUSTATIVE, _GUSTATIVE_NORM)
    d_s = _euclidean(profile_a, profile_b, DIMS_STRUCTURAL, _STRUCTURAL_NORM)
    total = gustative_weight * d_g + structural_weight * d_s

    details: list[PerDimensionDetail] = []
    for dim in DIMS_GUSTATIVE:
        va, vb = _clamp(profile_a[dim]), _clamp(profile_b[dim])
        delta = abs(va - vb)
        details.append(PerDimensionDetail(
            dimension=dim, group="gustative",
            value_a=va, value_b=vb,
            abs_delta=delta, squared_contribution=delta ** 2,
        ))
    for dim in DIMS_STRUCTURAL:
        va, vb = _clamp(profile_a[dim]), _clamp(profile_b[dim])
        delta = abs(va - vb)
        details.append(PerDimensionDetail(
            dimension=dim, group="structural",
            value_a=va, value_b=vb,
            abs_delta=delta, squared_contribution=delta ** 2,
        ))

    details.sort(key=lambda d: d.abs_delta, reverse=True)

    return FlavorBreakdownResult(
        total_distance=total,
        gustative_distance=d_g,
        structural_distance=d_s,
        weights={"gustative": gustative_weight, "structural": structural_weight},
        per_dimension=details,
    )


def aggregate_class_profile(
    bottle_profiles: list[dict[str, int]],
) -> dict[str, int]:
    """Median-per-dimension aggregate, clamped to 0-5.

    Raises ValueError when *bottle_profiles* is empty.
    """
    if not bottle_profiles:
        raise ValueError("Cannot aggregate zero profiles")

    result: dict[str, int] = {}
    for dim in DIMS_GUSTATIVE + DIMS_STRUCTURAL:
        values = [_clamp(p[dim]) for p in bottle_profiles]
        med = statistics.median(values)
        # Round half-to-even (Python default for round())
        result[dim] = max(0, min(_MAX_VAL, round(med)))
    return result
