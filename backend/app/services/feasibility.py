"""Feasibility logic — can-make-now computation.

Exposes two public functions that accept an *arbitrary* set of on-hand
class_ids so that Phase 4 (set-cover) can simulate "what if I added this
class?" without touching the DB.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.orm import Session

from app import queries


@dataclass
class FeasibilityResult:
    can_make: bool
    missing_count: int
    missing_classes: list[str]  # human-readable, alt groups as "X OR Y"


def _on_hand_class_ids_from_db(session: Session) -> set[int]:
    """Return the set of class_ids for which at least one bottle is on_hand."""
    rows = session.execute(
        text("SELECT DISTINCT class_id FROM bottle WHERE on_hand = TRUE")
    ).all()
    return {r[0] for r in rows}


def _build_class_hierarchy(session: Session) -> dict:
    """Build hierarchy lookups for generic class expansion.

    Returns a dict with:
      - 'parent_children': parent_id → set of child class_ids
      - 'class_parent': class_id → parent_id (or None)
      - 'class_names': class_id → name
      - 'generic_ids': set of class_ids whose name ends with '(generic)'
    """
    rows = session.execute(
        text("SELECT id, parent_id, name FROM ingredient_class")
    ).all()

    parent_children: dict[int, set[int]] = {}
    class_parent: dict[int, int | None] = {}
    class_names: dict[int, str] = {}
    generic_ids: set[int] = set()

    for cid, pid, name in rows:
        class_names[cid] = name
        class_parent[cid] = pid
        if name.endswith("(generic)"):
            generic_ids.add(cid)
        if pid is not None:
            parent_children.setdefault(pid, set()).add(cid)

    return {
        "parent_children": parent_children,
        "class_parent": class_parent,
        "class_names": class_names,
        "generic_ids": generic_ids,
    }


def _is_satisfied(
    class_id: int,
    on_hand_class_ids: set[int],
    hierarchy: dict,
) -> bool:
    """Check if a required class_id is satisfied by the on-hand inventory.

    Rules:
    - Exact match always works.
    - If the required class is a "(generic)" class, any sibling (child of
      the same parent) that is on-hand also satisfies it.
    """
    if class_id in on_hand_class_ids:
        return True

    if class_id in hierarchy["generic_ids"]:
        parent_id = hierarchy["class_parent"].get(class_id)
        if parent_id is not None:
            siblings = hierarchy["parent_children"].get(parent_id, set())
            if siblings & on_hand_class_ids:
                return True

    return False


def compute_feasibility(
    session: Session,
    on_hand_class_ids: set[int] | None = None,
) -> dict[int, FeasibilityResult]:
    """Compute feasibility for ALL recipes in one pass.

    If *on_hand_class_ids* is None, reads from the DB (bottle.on_hand=true).
    """
    if on_hand_class_ids is None:
        on_hand_class_ids = _on_hand_class_ids_from_db(session)

    # 1. Build class hierarchy for generic expansion
    hierarchy = _build_class_hierarchy(session)
    class_names = hierarchy["class_names"]

    # 2. Fetch all required (non-optional, non-garnish) ingredients
    req_rows = session.execute(queries.REQUIRED_INGREDIENTS).mappings().all()

    # 3. Fetch all recipes
    recipe_rows = session.execute(queries.ALL_RECIPES_BRIEF).mappings().all()
    recipe_ids = {r["id"] for r in recipe_rows}

    # 4. Group required ingredients by (recipe_id, requirement_key)
    #    requirement_key: alt_group_id if set, else "single:<ri.id>"
    @dataclass
    class Requirement:
        class_ids: list[int] = field(default_factory=list)
        class_names: list[str] = field(default_factory=list)
        satisfied: bool = False

    # recipe_id → list[Requirement]
    recipe_reqs: dict[int, dict[str, Requirement]] = {}
    for row in req_rows:
        rid = row["recipe_id"]
        alt = row["alternative_group_id"]
        key = str(alt) if alt is not None else f"s:{row['id']}"
        if rid not in recipe_reqs:
            recipe_reqs[rid] = {}
        if key not in recipe_reqs[rid]:
            recipe_reqs[rid][key] = Requirement()
        req = recipe_reqs[rid][key]
        req.class_ids.append(row["class_id"])
        req.class_names.append(class_names.get(row["class_id"], "?"))

    # 5. Evaluate
    results: dict[int, FeasibilityResult] = {}
    for rid in recipe_ids:
        reqs = recipe_reqs.get(rid, {})
        missing: list[str] = []
        for _key, req in reqs.items():
            if any(_is_satisfied(cid, on_hand_class_ids, hierarchy)
                   for cid in req.class_ids):
                continue
            # Not satisfied — build human-readable label
            if len(req.class_names) > 1:
                missing.append(" OR ".join(sorted(set(req.class_names))))
            else:
                missing.append(req.class_names[0])
        results[rid] = FeasibilityResult(
            can_make=len(missing) == 0,
            missing_count=len(missing),
            missing_classes=missing,
        )

    return results


def compute_single_recipe_feasibility(
    session: Session,
    recipe_id: int,
    on_hand_class_ids: set[int] | None = None,
) -> FeasibilityResult | None:
    """Compute feasibility for a single recipe. Returns None if recipe not found."""
    if on_hand_class_ids is None:
        on_hand_class_ids = _on_hand_class_ids_from_db(session)

    hierarchy = _build_class_hierarchy(session)

    rows = session.execute(
        queries.RECIPE_INGREDIENTS_FULL, {"recipe_id": recipe_id},
    ).mappings().all()

    if not rows:
        # Check if recipe even exists
        exists = session.execute(
            queries.RECIPE_BY_ID, {"recipe_id": recipe_id},
        ).mappings().first()
        if exists is None:
            return None
        # Recipe exists but has no ingredients — vacuously feasible
        return FeasibilityResult(can_make=True, missing_count=0, missing_classes=[])

    # Group by requirement key (only mandatory, non-garnish, non-commodity)
    @dataclass
    class Req:
        class_ids: list[int] = field(default_factory=list)
        class_names: list[str] = field(default_factory=list)

    reqs: dict[str, Req] = {}
    for row in rows:
        if row["is_optional"] or row["is_garnish"] or row["is_commodity"]:
            continue
        alt = row["alternative_group_id"]
        key = str(alt) if alt is not None else f"s:{row['class_id']}"
        if key not in reqs:
            reqs[key] = Req()
        reqs[key].class_ids.append(row["class_id"])
        reqs[key].class_names.append(row["class_name"])

    missing: list[str] = []
    for _key, req in reqs.items():
        if any(_is_satisfied(cid, on_hand_class_ids, hierarchy)
               for cid in req.class_ids):
            continue
        if len(req.class_names) > 1:
            missing.append(" OR ".join(sorted(set(req.class_names))))
        else:
            missing.append(req.class_names[0])

    return FeasibilityResult(
        can_make=len(missing) == 0,
        missing_count=len(missing),
        missing_classes=missing,
    )
