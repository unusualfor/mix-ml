"""Feasibility logic — can-make-now computation.

Match is strict on class_id, with one exception: required classes whose
name ends with " (generic)" act as wildcards over their siblings in the
taxonomy (same parent_id).  Example: a recipe requiring "Gin (generic)"
is satisfied by a bottle in "London Dry Gin" because both share the
"Gin" family root.  The reverse is not true: a recipe requiring
"London Dry Gin" is NOT satisfied by a bottle in "Gin (generic)".

Exposes two public functions that accept an *arbitrary* set of on-hand
class_ids so that Phase 4 (set-cover) can simulate "what if I added this
class?" without touching the DB.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.orm import Session

from app import queries
from app.services.inventory import get_on_hand_class_ids


@dataclass
class FeasibilityResult:
    can_make: bool
    missing_count: int
    missing_classes: list[str]  # human-readable, alt groups as "X OR Y"


def _on_hand_class_ids_from_db(session: Session) -> set[int]:
    """Return the set of class_ids for which at least one bottle is on_hand.

    Deprecated: prefer ``get_on_hand_class_ids`` from ``app.services.inventory``.
    Kept for backward compatibility with existing router imports.
    """
    return get_on_hand_class_ids(session)


def _build_class_hierarchy(session: Session) -> dict:
    """Build lookup tables for class names and parent relationships.

    Returns a dict with:
      - 'class_names': class_id → name
      - 'class_parent_ids': class_id → parent_id (or None)
    """
    rows = session.execute(
        text("SELECT id, name, parent_id FROM ingredient_class")
    ).all()

    class_names: dict[int, str] = {}
    class_parent_ids: dict[int, int | None] = {}
    for cid, name, parent_id in rows:
        class_names[cid] = name
        class_parent_ids[cid] = parent_id

    return {
        "class_names": class_names,
        "class_parent_ids": class_parent_ids,
    }


_GENERIC_SUFFIX = " (generic)"


def _is_satisfied(
    class_id: int,
    on_hand_class_ids: set[int],
    on_hand_parent_ids: set[int],
    class_names: dict[int, str],
    class_parent_ids: dict[int, int | None],
) -> bool:
    """Check if a required class_id is satisfied by the on-hand inventory.

    Rule 1: exact class_id match.
    Rule 2: if the required class name ends with " (generic)", any on-hand
             class sharing the same parent_id satisfies the requirement.
    The wildcard is asymmetric — see module docstring.
    """
    if class_id in on_hand_class_ids:
        return True
    name = class_names.get(class_id, "")
    if name.endswith(_GENERIC_SUFFIX):
        req_parent = class_parent_ids.get(class_id)
        if req_parent is not None and req_parent in on_hand_parent_ids:
            return True
    return False


@dataclass
class _Requirement:
    class_ids: list[int] = field(default_factory=list)
    class_names: list[str] = field(default_factory=list)


class _FeasibilityContext:
    """Pre-fetched DB data for repeated feasibility evaluations."""

    __slots__ = ("class_names", "class_parent_ids", "recipe_ids", "recipe_reqs")

    def __init__(
        self,
        class_names: dict[int, str],
        class_parent_ids: dict[int, int | None],
        recipe_ids: set[int],
        recipe_reqs: dict[int, dict[str, _Requirement]],
    ):
        self.class_names = class_names
        self.class_parent_ids = class_parent_ids
        self.recipe_ids = recipe_ids
        self.recipe_reqs = recipe_reqs

    @classmethod
    def from_session(cls, session: Session) -> _FeasibilityContext:
        hierarchy = _build_class_hierarchy(session)
        class_names = hierarchy["class_names"]
        class_parent_ids = hierarchy["class_parent_ids"]

        req_rows = session.execute(queries.REQUIRED_INGREDIENTS).mappings().all()
        recipe_rows = session.execute(queries.ALL_RECIPES_BRIEF).mappings().all()
        recipe_ids = {r["id"] for r in recipe_rows}

        recipe_reqs: dict[int, dict[str, _Requirement]] = {}
        for row in req_rows:
            rid = row["recipe_id"]
            alt = row["alternative_group_id"]
            key = str(alt) if alt is not None else f"s:{row['id']}"
            if rid not in recipe_reqs:
                recipe_reqs[rid] = {}
            if key not in recipe_reqs[rid]:
                recipe_reqs[rid][key] = _Requirement()
            req = recipe_reqs[rid][key]
            req.class_ids.append(row["class_id"])
            req.class_names.append(class_names.get(row["class_id"], "?"))

        return cls(class_names, class_parent_ids, recipe_ids, recipe_reqs)

    def evaluate(self, on_hand_class_ids: set[int]) -> dict[int, FeasibilityResult]:
        on_hand_parent_ids = {
            self.class_parent_ids.get(cid)
            for cid in on_hand_class_ids
        }
        on_hand_parent_ids.discard(None)

        results: dict[int, FeasibilityResult] = {}
        for rid in self.recipe_ids:
            reqs = self.recipe_reqs.get(rid, {})
            missing: list[str] = []
            for _key, req in reqs.items():
                if any(_is_satisfied(cid, on_hand_class_ids, on_hand_parent_ids,
                                     self.class_names, self.class_parent_ids)
                       for cid in req.class_ids):
                    continue
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


def compute_feasibility(
    session: Session,
    on_hand_class_ids: set[int] | None = None,
    *,
    _ctx: _FeasibilityContext | None = None,
) -> dict[int, FeasibilityResult]:
    """Compute feasibility for ALL recipes in one pass.

    Match is strict on class_id, with one exception: required classes
    named "X (generic)" act as wildcards over their direct siblings in
    the taxonomy (same parent_id).  Example: a recipe requiring
    "Gin (generic)" is satisfied by a bottle in "London Dry Gin" because
    both share the "Gin" family root.  The reverse is not true: a recipe
    requiring "London Dry Gin" is NOT satisfied by a bottle in
    "Gin (generic)".

    If *on_hand_class_ids* is None, reads from the DB (bottle.on_hand=true).
    Pass a pre-built *_ctx* to skip repeated DB queries (used by optimizer).
    """
    if on_hand_class_ids is None:
        on_hand_class_ids = _on_hand_class_ids_from_db(session)

    if _ctx is None:
        _ctx = _FeasibilityContext.from_session(session)

    return _ctx.evaluate(on_hand_class_ids)


def compute_single_recipe_feasibility(
    session: Session,
    recipe_id: int,
    on_hand_class_ids: set[int] | None = None,
) -> FeasibilityResult | None:
    """Compute feasibility for a single recipe. Returns None if recipe not found."""
    if on_hand_class_ids is None:
        on_hand_class_ids = _on_hand_class_ids_from_db(session)

    hierarchy = _build_class_hierarchy(session)
    class_names = hierarchy["class_names"]
    class_parent_ids = hierarchy["class_parent_ids"]
    on_hand_parent_ids = {class_parent_ids.get(cid) for cid in on_hand_class_ids}
    on_hand_parent_ids.discard(None)

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
        if any(_is_satisfied(cid, on_hand_class_ids, on_hand_parent_ids,
                             class_names, class_parent_ids)
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
