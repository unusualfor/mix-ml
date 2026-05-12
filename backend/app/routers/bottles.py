import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import (
    BottleCreate,
    BottleListResponse,
    BottleOut,
    BottlePatch,
    BulkBottleResult,
    EquivalentAlternative,
    OptimizeComputation,
    OptimizeCurrentState,
    OptimizeNextResponse,
    RankedCandidate,
    ShoppingCurrentState,
    ShoppingExplanation,
    ShoppingPlanResponse,
    ShoppingPurchase,
    ShoppingSolution,
    ShoppingVerifyResponse,
    ShoppingWeights,
    UnlockedRecipe,
)
from app import queries
from app.services.optimizer import compute_optimize_next
from app.services.shopping_optimizer import (
    compute_shopping_plan,
    compute_explanation,
)

router = APIRouter(tags=["bottles"])


def _resolve_class_id(db: Session, class_name: str) -> int:
    row = db.execute(queries.CLASS_BY_NAME, {"name": class_name}).first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Class '{class_name}' not found")
    return row[0]


def _bottle_out(row) -> BottleOut:
    d = dict(row)
    # flavor_profile comes as a dict from JSONB — already compatible
    return BottleOut(**d)


@router.post("/bottles", response_model=BottleOut, status_code=201)
def create_bottle(body: BottleCreate, db: Session = Depends(get_db)):
    class_id = _resolve_class_id(db, body.class_name)
    row = db.execute(queries.INSERT_BOTTLE, {
        "class_id": class_id,
        "brand": body.brand,
        "label": body.label,
        "abv": body.abv,
        "on_hand": body.on_hand,
        "flavor_profile": json.dumps(body.flavor_profile.model_dump()),
        "notes": body.notes,
    }).mappings().first()
    db.commit()
    # Re-fetch to get joined class_name and family_name
    full = db.execute(queries.BOTTLE_BY_ID, {"bottle_id": row["id"]}).mappings().first()
    return _bottle_out(full)


@router.get("/bottles", response_model=BottleListResponse)
def list_bottles(
    on_hand: bool | None = Query(None),
    class_name: str | None = Query(None),
    family: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    params = {
        "on_hand": str(on_hand).lower() if on_hand is not None else None,
        "class_name": class_name,
        "family": family,
        "limit": limit,
        "offset": offset,
    }
    total = db.execute(queries.BOTTLES_COUNT, params).scalar_one()
    rows = db.execute(queries.BOTTLES_LIST, params).mappings().all()
    return BottleListResponse(
        total=total,
        items=[_bottle_out(r) for r in rows],
    )


@router.get("/bottles/optimize-next", response_model=OptimizeNextResponse)
def optimize_next(
    top: int = Query(10, ge=1, le=50),
    include_zero: bool = Query(False),
    db: Session = Depends(get_db),
):
    result = compute_optimize_next(db, top=top, include_zero=include_zero)
    return OptimizeNextResponse(
        current_state=OptimizeCurrentState(
            on_hand_class_ids=result.on_hand_class_ids,
            currently_feasible=result.currently_feasible,
            currently_feasible_recipes=result.currently_feasible_names,
        ),
        ranked_candidates=[
            RankedCandidate(
                class_id=c.class_id,
                class_name=c.class_name,
                parent_family=c.parent_family,
                delta=c.delta,
                unlocked_recipes=[
                    UnlockedRecipe(id=rid, name=result.recipe_names[rid])
                    for rid in c.unlocked_recipe_ids
                ],
                equivalent_alternatives=[
                    EquivalentAlternative(
                        class_id=a.class_id,
                        class_name=a.class_name,
                        parent_family=a.parent_family,
                    )
                    for a in c.equivalent_alternatives
                ],
            )
            for c in result.candidates
        ],
        computation=OptimizeComputation(
            candidates_evaluated=result.candidates_evaluated,
            ms=result.elapsed_ms,
        ),
    )


@router.get("/bottles/optimize-shopping", response_model=ShoppingPlanResponse)
def optimize_shopping(
    budget: int = Query(..., ge=1, le=15),
    weight_unforgettable: float = Query(1.0, ge=0.0),
    weight_contemporary: float = Query(1.0, ge=0.0),
    weight_new_era: float = Query(1.0, ge=0.0),
    explain: bool = Query(False),
    solver_timeout_seconds: int = Query(30, ge=1, le=300),
    db: Session = Depends(get_db),
):
    result = compute_shopping_plan(
        db,
        budget=budget,
        weight_unforgettable=weight_unforgettable,
        weight_contemporary=weight_contemporary,
        weight_new_era=weight_new_era,
        explain=explain,
        solver_timeout_seconds=solver_timeout_seconds,
    )

    purchases = [
        ShoppingPurchase(
            class_id=p.class_id,
            class_name=p.class_name,
            parent_family=p.parent_family,
            equivalent_alternatives=[
                EquivalentAlternative(
                    class_id=a.class_id,
                    class_name=a.class_name,
                    parent_family=a.parent_family,
                )
                for a in result.equiv_alts.get(p.class_id, [])
            ],
        )
        for p in result.purchases
    ]

    explanation = None
    if explain:
        from app.services.feasibility import _FeasibilityContext
        from app.services.inventory import get_on_hand_class_ids
        on_hand = get_on_hand_class_ids(db)
        ctx = _FeasibilityContext.from_session(db)
        expl = compute_explanation(result, on_hand, ctx)
        explanation = ShoppingExplanation(**expl)

    return ShoppingPlanResponse(
        budget=result.budget,
        weights=ShoppingWeights(**result.weights),
        current_state=ShoppingCurrentState(
            feasible_recipes=result.current_feasible,
            on_hand_class_ids_count=result.on_hand_count,
        ),
        solution=ShoppingSolution(
            recommended_purchases=purchases,
            feasible_recipes_after=result.feasible_after,
            delta=result.delta,
            weighted_score=result.weighted_score,
            is_optimal=result.is_optimal,
            solver_status=result.solver_status,
            computation_time_ms=result.elapsed_ms,
        ),
        explanation=explanation,
    )


@router.get("/bottles/optimize-shopping/verify", response_model=ShoppingVerifyResponse)
def optimize_shopping_verify(
    db: Session = Depends(get_db),
):
    greedy = compute_optimize_next(db, top=1, include_zero=False)
    ilp = compute_shopping_plan(db, budget=1)

    greedy_top_name = greedy.candidates[0].class_name if greedy.candidates else None
    greedy_delta = greedy.candidates[0].delta if greedy.candidates else 0

    ilp_top_name = ilp.purchases[0].class_name if ilp.purchases else None
    ilp_delta = ilp.delta

    match = greedy_delta == ilp_delta

    return ShoppingVerifyResponse(
        greedy_top={"class_name": greedy_top_name, "delta": greedy_delta},
        ilp_top={
            "class_name": ilp_top_name,
            "delta": ilp_delta,
            "weighted_score": ilp.weighted_score,
        },
        match=match,
    )


@router.get("/bottles/{bottle_id}", response_model=BottleOut)
def get_bottle(bottle_id: int, db: Session = Depends(get_db)):
    row = db.execute(queries.BOTTLE_BY_ID, {"bottle_id": bottle_id}).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Bottle not found")
    return _bottle_out(row)


@router.patch("/bottles/{bottle_id}", response_model=BottleOut)
def patch_bottle(bottle_id: int, body: BottlePatch, db: Session = Depends(get_db)):
    existing = db.execute(queries.BOTTLE_BY_ID, {"bottle_id": bottle_id}).mappings().first()
    if existing is None:
        raise HTTPException(status_code=404, detail="Bottle not found")

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return _bottle_out(existing)

    set_clauses = []
    params = {"bottle_id": bottle_id}
    for field_name, value in updates.items():
        if field_name == "flavor_profile":
            set_clauses.append("flavor_profile = CAST(:flavor_profile AS jsonb)")
            params["flavor_profile"] = json.dumps(value.model_dump() if hasattr(value, "model_dump") else value)
        else:
            set_clauses.append(f"{field_name} = :{field_name}")
            params[field_name] = value

    from sqlalchemy import text
    db.execute(
        text(f"UPDATE bottle SET {', '.join(set_clauses)} WHERE id = :bottle_id"),
        params,
    )
    db.commit()
    row = db.execute(queries.BOTTLE_BY_ID, {"bottle_id": bottle_id}).mappings().first()
    return _bottle_out(row)


@router.delete("/bottles/{bottle_id}", status_code=204)
def delete_bottle(bottle_id: int, db: Session = Depends(get_db)):
    row = db.execute(queries.DELETE_BOTTLE, {"bottle_id": bottle_id}).first()
    db.commit()
    if row is None:
        raise HTTPException(status_code=404, detail="Bottle not found")
    return None


@router.post("/bottles/_bulk", response_model=BulkBottleResult)
def bulk_upsert_bottles(bodies: list[BottleCreate], db: Session = Depends(get_db)):
    inserted = 0
    errors = []
    for idx, body in enumerate(bodies):
        try:
            row = db.execute(queries.CLASS_BY_NAME, {"name": body.class_name}).first()
            if row is None:
                errors.append({"index": idx, "reason": f"class not found: {body.class_name}"})
                continue
            class_id = row[0]
            # Check for existing brand+label (upsert)
            existing = db.execute(queries.FIND_BOTTLE_BY_BRAND_LABEL, {
                "brand": body.brand, "label": body.label,
            }).first()
            if existing:
                db.execute(queries.UPDATE_BOTTLE_FULL, {
                    "bottle_id": existing[0],
                    "class_id": class_id,
                    "abv": body.abv,
                    "on_hand": body.on_hand,
                    "flavor_profile": json.dumps(body.flavor_profile.model_dump()),
                    "notes": body.notes,
                    "label": body.label,
                })
            else:
                db.execute(queries.INSERT_BOTTLE, {
                    "class_id": class_id,
                    "brand": body.brand,
                    "label": body.label,
                    "abv": body.abv,
                    "on_hand": body.on_hand,
                    "flavor_profile": json.dumps(body.flavor_profile.model_dump()),
                    "notes": body.notes,
                })
            db.commit()
            inserted += 1
        except Exception as exc:
            db.rollback()
            errors.append({"index": idx, "reason": str(exc)})
    return BulkBottleResult(inserted=inserted, errors=errors)
