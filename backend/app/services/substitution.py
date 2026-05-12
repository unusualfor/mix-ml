"""Similar-bottle search and recipe-substitution logic.

All functions accept a SQLAlchemy *Session* and return plain dicts or
dataclasses consumable by the routers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from app import queries
from app.services.feasibility import (
    _GENERIC_SUFFIX,
    _build_class_hierarchy,
    _is_satisfied,
)
from app.services.flavor import (
    DIMS_GUSTATIVE,
    DIMS_STRUCTURAL,
    aggregate_class_profile,
    flavor_distance,
)
from app.services.inventory import get_on_hand_class_ids

_ALL_DIMS = DIMS_GUSTATIVE + DIMS_STRUCTURAL


# ---------------------------------------------------------------------------
# internal helpers
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class _Bottle:
    id: int
    class_id: int
    class_name: str
    parent_id: int | None
    family_name: str | None
    brand: str
    label: str | None
    on_hand: bool
    flavor_profile: dict[str, int]


def _load_bottles(session: Session) -> list[_Bottle]:
    rows = session.execute(queries.ALL_BOTTLES_WITH_PROFILE).mappings().all()
    return [_Bottle(**dict(r)) for r in rows]


def _bottle_summary(b: _Bottle) -> dict:
    return {
        "id": b.id,
        "brand": b.brand,
        "label": b.label,
        "class_name": b.class_name,
        "parent_family": b.family_name,
    }


def _dim_deltas(
    pa: dict[str, int], pb: dict[str, int],
) -> list[tuple[str, int]]:
    """Return (dim, abs_delta) sorted ascending by delta then name."""
    return sorted(
        [(d, abs(pa.get(d, 0) - pb.get(d, 0))) for d in _ALL_DIMS],
        key=lambda x: (x[1], x[0]),
    )


def _top_shared(deltas: list[tuple[str, int]], n: int = 4) -> list[str]:
    return [d[0] for d in deltas[:n]]


def _top_differing(deltas: list[tuple[str, int]], n: int = 3) -> list[str]:
    rev = sorted(deltas, key=lambda x: (-x[1], x[0]))
    return [d[0] for d in rev if d[1] > 0][:n]


def _compute_pivot_profile(
    class_id: int,
    parent_id: int | None,
    class_name: str,
    all_bottles: list[_Bottle],
) -> tuple[dict[str, int] | None, str]:
    """Compute a reference profile for a class.

    Returns ``(profile, source_description)`` or ``(None, reason)``.
    """
    # Generic class → aggregate siblings
    if class_name.endswith(_GENERIC_SUFFIX) and parent_id is not None:
        profiles = [
            b.flavor_profile for b in all_bottles
            if b.parent_id == parent_id and b.class_id != class_id
        ]
        if profiles:
            return (
                aggregate_class_profile(profiles),
                f"aggregated from {len(profiles)} sibling bottle(s) of {class_name}",
            )
        return None, "no reference profile available"

    # Direct: bottles in the exact class
    profiles = [b.flavor_profile for b in all_bottles if b.class_id == class_id]
    if profiles:
        return (
            aggregate_class_profile(profiles),
            f"aggregated from {len(profiles)} bottle(s) in {class_name}",
        )

    # Fallback: sibling classes (same parent_id)
    if parent_id is not None:
        profiles = [
            b.flavor_profile for b in all_bottles
            if b.parent_id == parent_id and b.class_id != class_id
        ]
        if profiles:
            return (
                aggregate_class_profile(profiles),
                f"aggregated from {len(profiles)} sibling bottle(s) of family",
            )

    return None, "no reference profile available"


def _satisfying_bottles(
    class_id: int,
    class_name: str,
    parent_id: int | None,
    on_hand_bottles: list[_Bottle],
) -> list[dict]:
    """Find on-hand bottles that satisfy a required class (exact + generic wildcard)."""
    result = []
    for b in on_hand_bottles:
        if b.class_id == class_id:
            result.append({"id": b.id, "brand": b.brand, "label": b.label})
        elif class_name.endswith(_GENERIC_SUFFIX):
            if parent_id is not None and b.parent_id == parent_id:
                result.append({"id": b.id, "brand": b.brand, "label": b.label})
    return result


# ---------------------------------------------------------------------------
# public: similar bottles
# ---------------------------------------------------------------------------

def compute_similar_bottles(
    session: Session,
    pivot_id: int,
    *,
    top: int = 10,
    max_distance: float | None = None,
    same_family_only: bool = False,
) -> dict | None:
    """Return ranked similar bottles. Returns None if pivot not found."""
    all_bottles = _load_bottles(session)
    pivot = next((b for b in all_bottles if b.id == pivot_id), None)
    if pivot is None:
        return None

    candidates: list[tuple[float, _Bottle]] = []
    for b in all_bottles:
        if b.id == pivot_id:
            continue
        if same_family_only and b.parent_id != pivot.parent_id:
            continue
        d = flavor_distance(pivot.flavor_profile, b.flavor_profile)
        if max_distance is not None and d > max_distance:
            continue
        candidates.append((d, b))

    candidates.sort(key=lambda x: (x[0], x[1].brand, x[1].label or ""))
    candidates = candidates[:top]

    results = []
    for d, b in candidates:
        deltas = _dim_deltas(pivot.flavor_profile, b.flavor_profile)
        results.append({
            "bottle": _bottle_summary(b),
            "distance": round(d, 4),
            "same_family": b.parent_id == pivot.parent_id and pivot.parent_id is not None,
            "top_shared_dimensions": _top_shared(deltas),
            "top_differing_dimensions": _top_differing(deltas),
        })

    return {
        "pivot": _bottle_summary(pivot),
        "results": results,
    }


# ---------------------------------------------------------------------------
# public: substitutions
# ---------------------------------------------------------------------------

def compute_substitutions(
    session: Session,
    recipe_id: int,
    *,
    tier: str = "both",
    strict_threshold: float = 0.25,
    loose_threshold: float = 0.20,
    include_satisfied: bool = False,
) -> dict | None:
    """Compute substitution suggestions. Returns None if recipe not found."""
    # Load recipe
    recipe_row = session.execute(
        queries.RECIPE_BY_ID, {"recipe_id": recipe_id},
    ).mappings().first()
    if recipe_row is None:
        return None

    # Load recipe ingredients (rich)
    ri_rows = session.execute(
        queries.RECIPE_INGREDIENTS_FOR_SUBSTITUTION, {"recipe_id": recipe_id},
    ).mappings().all()

    # Count total ingredients for RecipeListItem
    total_ingredients = len(ri_rows)

    # Load bottles and hierarchy
    all_bottles = _load_bottles(session)
    on_hand_ids = get_on_hand_class_ids(session)
    hierarchy = _build_class_hierarchy(session)
    class_names = hierarchy["class_names"]
    class_parent_ids = hierarchy["class_parent_ids"]

    on_hand_parent_ids = {
        class_parent_ids.get(cid) for cid in on_hand_ids
    }
    on_hand_parent_ids.discard(None)

    on_hand_bottles = [b for b in all_bottles if b.on_hand]

    # Filter to mandatory, non-garnish, non-commodity
    relevant = [
        dict(r) for r in ri_rows
        if not r["is_optional"] and not r["is_garnish"] and not r["is_commodity"]
    ]

    # Group by alternative_group_id
    groups: dict[str, list[dict]] = {}
    for ri in relevant:
        alt = ri["alternative_group_id"]
        key = str(alt) if alt is not None else f"s:{ri['recipe_ingredient_id']}"
        groups.setdefault(key, []).append(ri)

    # All class_ids in the recipe (for anti-doppione)
    all_recipe_class_ids = {r["class_id"] for r in ri_rows}

    # Compute feasibility
    from app.services.feasibility import compute_single_recipe_feasibility
    feas = compute_single_recipe_feasibility(session, recipe_id, on_hand_ids)
    current_feas = {
        "can_make": feas.can_make if feas else False,
        "missing_count": feas.missing_count if feas else 0,
    }

    analysis: list[dict] = []

    for _key, group_members in groups.items():
        is_alt_group = len(group_members) > 1

        # Check if any member of the group is satisfied
        group_satisfied = any(
            _is_satisfied(
                m["class_id"], on_hand_ids, on_hand_parent_ids,
                class_names, class_parent_ids,
            )
            for m in group_members
        )

        if group_satisfied and not include_satisfied:
            continue

        if group_satisfied:
            # Find satisfying bottles for the satisfied member(s)
            sat_bottles: list[dict] = []
            for m in group_members:
                sat_bottles.extend(
                    _satisfying_bottles(
                        m["class_id"], m["class_name"], m["parent_id"],
                        on_hand_bottles,
                    )
                )
            # Deduplicate by id
            seen_ids: set[int] = set()
            unique_sat: list[dict] = []
            for sb in sat_bottles:
                if sb["id"] not in seen_ids:
                    seen_ids.add(sb["id"])
                    unique_sat.append(sb)

            rep = group_members[0]
            analysis.append({
                "recipe_ingredient_id": rep["recipe_ingredient_id"],
                "class_name": rep["class_name"],
                "parent_family": rep["parent_family"],
                "amount": float(rep["amount"]) if rep["amount"] is not None else None,
                "unit": rep["unit"],
                "is_satisfied": True,
                "satisfied_by_bottles": unique_sat,
            })
            continue

        # Not satisfied — compute substitutions
        # Pick representative: first alphabetically by class_name
        rep = min(group_members, key=lambda m: m["class_name"])

        # Anti-doppione: all other class_ids in the recipe (exclude this group)
        group_class_ids = {m["class_id"] for m in group_members}
        anti_doppione_ids = all_recipe_class_ids - group_class_ids
        anti_doppione_names = sorted(
            class_names.get(cid, "?") for cid in anti_doppione_ids
        )

        # Pivot profile
        pivot_profile, _pivot_source = _compute_pivot_profile(
            rep["class_id"], rep["parent_id"], rep["class_name"], all_bottles,
        )

        subs: dict[str, list] = {"strict": [], "loose": []}
        if pivot_profile is not None:
            for b in on_hand_bottles:
                if b.class_id in anti_doppione_ids:
                    continue
                d = flavor_distance(pivot_profile, b.flavor_profile)
                same_parent = (
                    b.parent_id is not None
                    and b.parent_id == rep["parent_id"]
                )
                if same_parent:
                    if d > strict_threshold:
                        continue
                    if tier in ("strict", "both"):
                        subs["strict"].append({
                            "bottle": _bottle_summary(b),
                            "distance": round(d, 4),
                            "tier": "strict",
                            "rationale": f"Same family ({b.family_name or '?'}), distance {d:.2f}",
                        })
                else:
                    if d > loose_threshold:
                        continue
                    if tier in ("loose", "both"):
                        subs["loose"].append({
                            "bottle": _bottle_summary(b),
                            "distance": round(d, 4),
                            "tier": "loose",
                            "rationale": f"Cross-family ({b.family_name or '?'} → {rep['parent_family'] or '?'}), distance {d:.2f}",
                        })

            subs["strict"].sort(key=lambda x: x["distance"])
            subs["loose"].sort(key=lambda x: x["distance"])
            subs["strict"] = subs["strict"][:5]
            subs["loose"] = subs["loose"][:5]

        entry: dict = {
            "recipe_ingredient_id": rep["recipe_ingredient_id"],
            "class_name": rep["class_name"],
            "parent_family": rep["parent_family"],
            "amount": float(rep["amount"]) if rep["amount"] is not None else None,
            "unit": rep["unit"],
            "is_satisfied": False,
            "anti_doppione_classes": anti_doppione_names,
            "substitutions": subs,
        }
        notes: list[str] = []
        if is_alt_group:
            alt_names = sorted({m["class_name"] for m in group_members})
            notes.append(
                f"alternative group, suggestions apply to any of "
                f"[{', '.join(alt_names)}]"
            )
        if pivot_profile is None:
            notes.append("no reference profile available")
        if notes:
            entry["note"] = "; ".join(notes)
        analysis.append(entry)

    return {
        "recipe": {
            "id": recipe_row["id"],
            "name": recipe_row["name"],
            "iba_category": recipe_row["iba_category"],
            "glass": recipe_row["glass"],
            "ingredient_count": total_ingredients,
        },
        "current_feasibility": current_feas,
        "ingredients_analysis": analysis,
    }


# ---------------------------------------------------------------------------
# public: substitution trace (diagnostic)
# ---------------------------------------------------------------------------

def compute_substitution_trace(
    session: Session,
    recipe_id: int,
    recipe_ingredient_id: int,
) -> dict | None:
    """Diagnostic trace for a single recipe ingredient substitution."""
    ri_rows = session.execute(
        queries.RECIPE_INGREDIENTS_FOR_SUBSTITUTION, {"recipe_id": recipe_id},
    ).mappings().all()
    if not ri_rows:
        return None

    target = next(
        (dict(r) for r in ri_rows if r["recipe_ingredient_id"] == recipe_ingredient_id),
        None,
    )
    if target is None:
        return None

    all_bottles = _load_bottles(session)
    on_hand_bottles = [b for b in all_bottles if b.on_hand]

    # Anti-doppione
    all_recipe_class_ids = {r["class_id"] for r in ri_rows}
    anti_doppione_ids = all_recipe_class_ids - {target["class_id"]}

    # Pivot
    pivot_profile, pivot_source = _compute_pivot_profile(
        target["class_id"], target["parent_id"], target["class_name"],
        all_bottles,
    )

    bottle_details: list[dict] = []
    for b in on_hand_bottles:
        if pivot_profile is None:
            bottle_details.append({
                "bottle": _bottle_summary(b),
                "distance": 0.0,
                "included": False,
                "exclusion_reason": "no pivot profile available",
            })
            continue

        d = flavor_distance(pivot_profile, b.flavor_profile)
        same_parent = b.parent_id is not None and b.parent_id == target["parent_id"]

        if b.class_id in anti_doppione_ids:
            bottle_details.append({
                "bottle": _bottle_summary(b),
                "distance": round(d, 4),
                "included": False,
                "exclusion_reason": f"anti-doppione (class {b.class_name} used elsewhere in recipe)",
            })
        elif same_parent and d <= 0.25:
            bottle_details.append({
                "bottle": _bottle_summary(b),
                "distance": round(d, 4),
                "included": True,
                "tier": "strict",
            })
        elif not same_parent and d <= 0.20:
            bottle_details.append({
                "bottle": _bottle_summary(b),
                "distance": round(d, 4),
                "included": True,
                "tier": "loose",
            })
        else:
            reason = (
                f"distance {d:.2f} exceeds "
                f"{'strict' if same_parent else 'loose'} threshold"
            )
            bottle_details.append({
                "bottle": _bottle_summary(b),
                "distance": round(d, 4),
                "included": False,
                "exclusion_reason": reason,
            })

    return {
        "recipe_ingredient_id": recipe_ingredient_id,
        "class_name": target["class_name"],
        "pivot_profile": pivot_profile,
        "pivot_source": pivot_source,
        "on_hand_bottles": bottle_details,
    }
