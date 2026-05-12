"""Single-step greedy set-cover optimizer.

Answers: "Which single bottle class should I buy next to unlock
the most new IBA cocktails?"
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app import queries
from app.services.feasibility import compute_feasibility, _FeasibilityContext
from app.services.inventory import get_on_hand_class_ids


_GENERIC_SUFFIX = " (generic)"


@dataclass
class _CandidateResult:
    class_id: int
    class_name: str
    parent_id: int | None
    parent_family: str | None
    delta: int
    unlocked_recipe_ids: list[int] = field(default_factory=list)


@dataclass
class _EquivalentAlt:
    class_id: int
    class_name: str
    parent_family: str | None


@dataclass
class _GroupedCandidate:
    class_id: int
    class_name: str
    parent_family: str | None
    delta: int
    unlocked_recipe_ids: list[int]
    equivalent_alternatives: list[_EquivalentAlt] = field(default_factory=list)


@dataclass
class OptimizeNextResult:
    on_hand_class_ids: list[int]
    currently_feasible: int
    currently_feasible_recipe_ids: set[int]
    currently_feasible_names: list[str]
    candidates: list[_GroupedCandidate]
    candidates_evaluated: int
    elapsed_ms: int
    # recipe_id → name lookup for unlocked recipes
    recipe_names: dict[int, str]


def compute_optimize_next(
    session: Session,
    top: int = 10,
    include_zero: bool = False,
) -> OptimizeNextResult:
    t0 = time.monotonic()

    on_hand = get_on_hand_class_ids(session)

    # Pre-fetch feasibility context once (3 DB queries),
    # then reuse for all candidate evaluations (pure Python).
    ctx = _FeasibilityContext.from_session(session)

    # Current feasibility baseline
    current = compute_feasibility(session, on_hand, _ctx=ctx)
    current_feasible_ids = {
        rid for rid, res in current.items() if res.can_make
    }

    # Recipe id→name map (needed for output)
    recipe_rows = session.execute(queries.ALL_RECIPES_BRIEF).mappings().all()
    recipe_names = {r["id"]: r["name"] for r in recipe_rows}

    currently_feasible_names = sorted(
        recipe_names[rid] for rid in current_feasible_ids if rid in recipe_names
    )

    # Candidate classes
    cand_rows = session.execute(queries.CANDIDATE_CLASSES).mappings().all()
    candidates_all = [
        dict(r) for r in cand_rows if r["id"] not in on_hand
    ]

    # Evaluate each candidate
    results: list[_CandidateResult] = []
    for cand in candidates_all:
        hypothetical = on_hand | {cand["id"]}
        hypo_feasibility = compute_feasibility(session, hypothetical, _ctx=ctx)
        hypo_feasible_ids = {
            rid for rid, res in hypo_feasibility.items() if res.can_make
        }
        unlocked = sorted(hypo_feasible_ids - current_feasible_ids)
        delta = len(unlocked)

        if delta == 0 and not include_zero:
            continue

        results.append(_CandidateResult(
            class_id=cand["id"],
            class_name=cand["name"],
            parent_id=cand["parent_id"],
            parent_family=cand["parent_family"],
            delta=delta,
            unlocked_recipe_ids=unlocked,
        ))

    # -- Group equivalent candidates --
    # Two candidates are equivalent iff they share parent_id AND
    # unlock the exact same set of recipes.
    groups: dict[tuple, list[_CandidateResult]] = {}
    for c in results:
        key = (c.parent_id, frozenset(c.unlocked_recipe_ids))
        groups.setdefault(key, []).append(c)

    grouped: list[_GroupedCandidate] = []
    for members in groups.values():
        # Pick representative: prefer " (generic)" suffix, else alphabetical
        generics = [m for m in members if m.class_name.endswith(_GENERIC_SUFFIX)]
        if generics:
            rep = generics[0]
        else:
            members.sort(key=lambda m: m.class_name)
            rep = members[0]

        alts = sorted(
            [
                _EquivalentAlt(
                    class_id=m.class_id,
                    class_name=m.class_name,
                    parent_family=m.parent_family,
                )
                for m in members if m.class_id != rep.class_id
            ],
            key=lambda a: a.class_name,
        )

        grouped.append(_GroupedCandidate(
            class_id=rep.class_id,
            class_name=rep.class_name,
            parent_family=rep.parent_family,
            delta=rep.delta,
            unlocked_recipe_ids=rep.unlocked_recipe_ids,
            equivalent_alternatives=alts,
        ))

    # Sort: delta descending, then class_name ascending
    grouped.sort(key=lambda c: (-c.delta, c.class_name))

    # Truncate (top counts groups, not raw candidates)
    grouped = grouped[:top]

    elapsed_ms = int((time.monotonic() - t0) * 1000)

    return OptimizeNextResult(
        on_hand_class_ids=sorted(on_hand),
        currently_feasible=len(current_feasible_ids),
        currently_feasible_recipe_ids=current_feasible_ids,
        currently_feasible_names=currently_feasible_names,
        candidates=grouped,
        candidates_evaluated=len(candidates_all),
        elapsed_ms=elapsed_ms,
        recipe_names=recipe_names,
    )
