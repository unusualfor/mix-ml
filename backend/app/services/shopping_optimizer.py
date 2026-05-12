"""Multi-step shopping planner via CP-SAT (Integer Linear Programming).

Given a budget of K bottles to buy, finds the set of ingredient-class
purchases that maximises the (weighted) number of newly feasible IBA
cocktails.  Generalises the greedy single-step ``optimize-next`` to
arbitrary K using Google OR-Tools CP-SAT solver.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from ortools.sat.python import cp_model
from sqlalchemy.orm import Session

from app import queries
from app.services.feasibility import (
    _FeasibilityContext,
    _is_satisfied,
    _GENERIC_SUFFIX,
    compute_feasibility,
)
from app.services.inventory import get_on_hand_class_ids

logger = logging.getLogger(__name__)

_WEIGHT_SCALE = 1000  # CP-SAT needs integers; floats × 1000 then round


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class _Purchase:
    class_id: int
    class_name: str
    parent_family: str | None


@dataclass
class _EquivAlt:
    class_id: int
    class_name: str
    parent_family: str | None


@dataclass
class ShoppingPlanResult:
    budget: int
    weights: dict[str, float]
    on_hand_count: int
    current_feasible: int
    current_feasible_ids: set[int]
    purchases: list[_Purchase]
    equiv_alts: dict[int, list[_EquivAlt]]  # class_id → alternatives
    feasible_after: int
    feasible_after_ids: set[int]
    delta: int
    weighted_score: float
    is_optimal: bool
    solver_status: str
    elapsed_ms: int
    # for explanation
    recipe_names: dict[int, str]
    recipe_categories: dict[int, str]


# ---------------------------------------------------------------------------
# Core solver
# ---------------------------------------------------------------------------

def compute_shopping_plan(
    session: Session,
    budget: int,
    weight_unforgettable: float = 1.0,
    weight_contemporary: float = 1.0,
    weight_new_era: float = 1.0,
    explain: bool = False,
    solver_timeout_seconds: int = 30,
) -> ShoppingPlanResult:
    t0 = time.monotonic()

    weights_map = {
        "unforgettable": weight_unforgettable,
        "contemporary": weight_contemporary,
        "new_era": weight_new_era,
    }

    on_hand = get_on_hand_class_ids(session)
    ctx = _FeasibilityContext.from_session(session)

    # Current baseline
    current = compute_feasibility(session, on_hand, _ctx=ctx)
    current_feasible_ids = {rid for rid, r in current.items() if r.can_make}

    # Recipe metadata
    recipe_rows = session.execute(queries.ALL_RECIPES_BRIEF).mappings().all()
    recipe_names = {r["id"]: r["name"] for r in recipe_rows}
    recipe_categories = {r["id"]: r["iba_category"] for r in recipe_rows}
    all_recipe_ids = {r["id"] for r in recipe_rows}

    # Not-yet-feasible recipes
    not_feasible_ids = all_recipe_ids - current_feasible_ids

    # Candidate classes (same logic as optimize-next)
    cand_rows = session.execute(queries.CANDIDATE_CLASSES).mappings().all()
    candidates = {r["id"]: dict(r) for r in cand_rows if r["id"] not in on_hand}
    candidate_ids = set(candidates.keys())

    # Pre-compute on_hand parent_ids for _is_satisfied
    on_hand_parent_ids = {
        ctx.class_parent_ids.get(cid) for cid in on_hand
    }
    on_hand_parent_ids.discard(None)

    # ---------------------------------------------------------------
    # Build coverage map: for each recipe requirement, which candidate
    # classes would satisfy it?
    # ---------------------------------------------------------------
    # recipe_id → list of requirements
    # each requirement = set of candidate class_ids that can fill it
    # (empty if already satisfied or impossible)
    recipe_reqs_coverage: dict[int, list[set[int]]] = {}

    for rid in not_feasible_ids:
        reqs = ctx.recipe_reqs.get(rid, {})
        coverage: list[set[int]] = []
        impossible = False

        for _key, req in reqs.items():
            # Check if already satisfied by on_hand
            if any(
                _is_satisfied(
                    cid, on_hand, on_hand_parent_ids,
                    ctx.class_names, ctx.class_parent_ids,
                )
                for cid in req.class_ids
            ):
                continue  # requirement already met

            # Find which candidates can satisfy this requirement
            satisfying: set[int] = set()
            for cid in req.class_ids:
                # Direct match
                if cid in candidate_ids:
                    satisfying.add(cid)
                # Wildcard: if class is "(generic)", any sibling candidate works
                name = ctx.class_names.get(cid, "")
                if name.endswith(_GENERIC_SUFFIX):
                    req_parent = ctx.class_parent_ids.get(cid)
                    if req_parent is not None:
                        for cc in candidate_ids:
                            if ctx.class_parent_ids.get(cc) == req_parent:
                                satisfying.add(cc)
                # Reverse: if a candidate is "(generic)" with same parent,
                # it does NOT satisfy a specific requirement (asymmetric)
                # — already handled by _is_satisfied logic

            if not satisfying:
                impossible = True
                break

            coverage.append(satisfying)

        if impossible:
            continue  # skip recipe, can't be made even buying everything

        if not coverage:
            continue  # all requirements already satisfied (shouldn't be here)

        recipe_reqs_coverage[rid] = coverage

    # ---------------------------------------------------------------
    # Build CP-SAT model
    # ---------------------------------------------------------------
    model = cp_model.CpModel()

    x = {c: model.new_bool_var(f"buy_{c}") for c in candidate_ids}
    y = {r: model.new_bool_var(f"feasible_{r}") for r in recipe_reqs_coverage}

    # Budget constraint
    model.add(sum(x[c] for c in candidate_ids) <= budget)

    # Coverage constraints
    for rid, coverage in recipe_reqs_coverage.items():
        for satisfying_set in coverage:
            cands_in_model = [c for c in satisfying_set if c in x]
            if not cands_in_model:
                model.add(y[rid] == 0)
                break
            model.add(y[rid] <= sum(x[c] for c in cands_in_model))

    # Objective: maximize weighted recipe count
    obj_terms = []
    for rid in recipe_reqs_coverage:
        cat = recipe_categories.get(rid, "contemporary")
        w = weights_map.get(cat, 1.0)
        coeff = int(round(w * _WEIGHT_SCALE))
        if coeff > 0:
            obj_terms.append(coeff * y[rid])
    model.maximize(sum(obj_terms))

    # ---------------------------------------------------------------
    # Solve
    # ---------------------------------------------------------------
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = solver_timeout_seconds

    status = solver.solve(model)

    status_name = {
        cp_model.OPTIMAL: "OPTIMAL",
        cp_model.FEASIBLE: "FEASIBLE",
        cp_model.INFEASIBLE: "INFEASIBLE",
        cp_model.MODEL_INVALID: "MODEL_INVALID",
        cp_model.UNKNOWN: "UNKNOWN",
    }.get(status, f"STATUS_{status}")

    is_optimal = status == cp_model.OPTIMAL

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        # Return empty solution
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        return ShoppingPlanResult(
            budget=budget,
            weights=weights_map,
            on_hand_count=len(on_hand),
            current_feasible=len(current_feasible_ids),
            current_feasible_ids=current_feasible_ids,
            purchases=[],
            equiv_alts={},
            feasible_after=len(current_feasible_ids),
            feasible_after_ids=current_feasible_ids,
            delta=0,
            weighted_score=0.0,
            is_optimal=False,
            solver_status=status_name,
            elapsed_ms=elapsed_ms,
            recipe_names=recipe_names,
            recipe_categories=recipe_categories,
        )

    # Extract solution
    purchased_ids = sorted(c for c in candidate_ids if solver.value(x[c]) == 1)
    solver_newly_feasible = {
        r for r in recipe_reqs_coverage if solver.value(y[r]) == 1
    }

    # Build purchase objects
    purchases = [
        _Purchase(
            class_id=c,
            class_name=candidates[c]["name"],
            parent_family=candidates[c]["parent_family"],
        )
        for c in purchased_ids
    ]

    # Equivalent alternatives (same parent + same set of unlocked recipes)
    hypothetical = on_hand | set(purchased_ids)
    hypo_feas = compute_feasibility(session, hypothetical, _ctx=ctx)
    hypo_feasible_ids = {rid for rid, r in hypo_feas.items() if r.can_make}
    actual_newly = hypo_feasible_ids - current_feasible_ids

    # Safety check: ILP vs SQL divergence
    ilp_newly_count = len(solver_newly_feasible)
    sql_newly_count = len(actual_newly)
    if ilp_newly_count != sql_newly_count:
        logger.warning(
            "ILP/SQL divergence: ILP says %d newly feasible, "
            "SQL says %d (diff=%d)",
            ilp_newly_count, sql_newly_count,
            ilp_newly_count - sql_newly_count,
        )

    # Compute equivalent alternatives per purchase
    equiv_alts = _compute_equiv_alts(
        purchased_ids, candidates, candidate_ids, on_hand,
        ctx, current_feasible_ids,
    )

    # Weighted score
    weighted_score = sum(
        weights_map.get(recipe_categories.get(rid, "contemporary"), 1.0)
        for rid in actual_newly
    )

    elapsed_ms = int((time.monotonic() - t0) * 1000)

    return ShoppingPlanResult(
        budget=budget,
        weights=weights_map,
        on_hand_count=len(on_hand),
        current_feasible=len(current_feasible_ids),
        current_feasible_ids=current_feasible_ids,
        purchases=purchases,
        equiv_alts=equiv_alts,
        feasible_after=len(hypo_feasible_ids),
        feasible_after_ids=hypo_feasible_ids,
        delta=len(actual_newly),
        weighted_score=round(weighted_score, 2),
        is_optimal=is_optimal,
        solver_status=status_name,
        elapsed_ms=elapsed_ms,
        recipe_names=recipe_names,
        recipe_categories=recipe_categories,
    )


# ---------------------------------------------------------------------------
# Equivalent alternatives (dedup like optimize-next)
# ---------------------------------------------------------------------------

def _compute_equiv_alts(
    purchased_ids: list[int],
    candidates: dict[int, dict],
    candidate_ids: set[int],
    on_hand: set[int],
    ctx: _FeasibilityContext,
    current_feasible_ids: set[int],
) -> dict[int, list[_EquivAlt]]:
    """For each purchased class, find sibling classes that unlock
    the exact same set of recipes (equivalent picks)."""

    # Compute unlocked set for each purchased class
    purchased_unlocked: dict[int, frozenset[int]] = {}
    for cid in purchased_ids:
        hypo = on_hand | {cid}
        feas = ctx.evaluate(hypo)
        unlocked = frozenset(
            rid for rid, r in feas.items()
            if r.can_make and rid not in current_feasible_ids
        )
        purchased_unlocked[cid] = unlocked

    result: dict[int, list[_EquivAlt]] = {}
    for cid in purchased_ids:
        parent_id = candidates[cid].get("parent_id")
        if parent_id is None:
            result[cid] = []
            continue

        alts = []
        for other_cid in candidate_ids:
            if other_cid == cid or other_cid in on_hand:
                continue
            if candidates.get(other_cid, {}).get("parent_id") != parent_id:
                continue
            # Check same unlocked set
            hypo = on_hand | {other_cid}
            feas = ctx.evaluate(hypo)
            other_unlocked = frozenset(
                rid for rid, r in feas.items()
                if r.can_make and rid not in current_feasible_ids
            )
            if other_unlocked == purchased_unlocked[cid]:
                alts.append(_EquivAlt(
                    class_id=other_cid,
                    class_name=candidates[other_cid]["name"],
                    parent_family=candidates[other_cid]["parent_family"],
                ))
        alts.sort(key=lambda a: a.class_name)
        result[cid] = alts

    return result


# ---------------------------------------------------------------------------
# Explanation: marginal value decomposition + coverage
# ---------------------------------------------------------------------------

def compute_explanation(
    result: ShoppingPlanResult,
    on_hand: set[int],
    ctx: _FeasibilityContext,
) -> dict:
    """Build the explanation dict for newly-feasible recipes and
    marginal value decomposition."""

    purchased_ids = [p.class_id for p in result.purchases]
    newly_feasible = result.feasible_after_ids - result.current_feasible_ids
    weights_map = result.weights

    # ---------------------------------------------------------------
    # 1. For each newly feasible recipe, which purchases contribute?
    # ---------------------------------------------------------------
    newly_recipes: list[dict] = []
    for rid in sorted(newly_feasible):
        contributors = []
        for p in result.purchases:
            # Would removing this purchase make the recipe infeasible?
            hypo = on_hand | {c for c in purchased_ids if c != p.class_id}
            feas = ctx.evaluate(hypo)
            if not feas[rid].can_make:
                contributors.append(p.class_name)
        # If no single purchase is individually necessary (redundant coverage),
        # list all purchases that could contribute
        if not contributors:
            contributors = [p.class_name for p in result.purchases]

        newly_recipes.append({
            "recipe_id": rid,
            "recipe_name": result.recipe_names.get(rid, "?"),
            "iba_category": result.recipe_categories.get(rid, "?"),
            "covered_by_purchases": contributors,
        })
    newly_recipes.sort(key=lambda r: r["recipe_name"])

    # ---------------------------------------------------------------
    # 2. Marginal value decomposition (greedy attribution)
    # ---------------------------------------------------------------
    marginal: list[dict] = []
    remaining_purchases = list(purchased_ids)
    accumulated = set(on_hand)
    attributed_recipes: set[int] = set()

    while remaining_purchases:
        # Pick the purchase from the plan that unlocks the most NEW recipes
        best_cid = None
        best_new: set[int] = set()
        best_weighted = 0.0

        for cid in remaining_purchases:
            hypo = accumulated | {cid}
            feas = ctx.evaluate(hypo)
            new_ids = {
                rid for rid, r in feas.items()
                if r.can_make
                and rid not in result.current_feasible_ids
                and rid not in attributed_recipes
            }
            w = sum(
                weights_map.get(
                    result.recipe_categories.get(rid, "contemporary"), 1.0
                )
                for rid in new_ids
            )
            if best_cid is None or w > best_weighted or (
                w == best_weighted and len(new_ids) > len(best_new)
            ):
                best_cid = cid
                best_new = new_ids
                best_weighted = w

        if best_cid is None:
            break

        cname = next(
            (p.class_name for p in result.purchases if p.class_id == best_cid),
            "?",
        )
        marginal.append({
            "class_name": cname,
            "incremental_recipes_unlocked": len(best_new),
            "incremental_weighted_value": round(best_weighted, 2),
        })
        accumulated.add(best_cid)
        attributed_recipes |= best_new
        remaining_purchases.remove(best_cid)

    return {
        "newly_feasible_recipes": newly_recipes,
        "purchases_marginal_value": marginal,
    }
