from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app import queries
from app.services.flavor import flavor_breakdown
from app.services.substitution import (
    compute_similar_bottles,
    compute_substitution_trace,
)

router = APIRouter(tags=["flavor"])


@router.get("/flavor/distance")
def distance(
    bottle_a: int = Query(...),
    bottle_b: int = Query(...),
    gustative_weight: float = Query(0.7),
    structural_weight: float = Query(0.3),
    db: Session = Depends(get_db),
):
    if abs((gustative_weight + structural_weight) - 1.0) > 1e-6:
        raise HTTPException(
            status_code=422,
            detail=(
                f"gustative_weight + structural_weight must sum to 1 "
                f"(got {gustative_weight} + {structural_weight} "
                f"= {gustative_weight + structural_weight})"
            ),
        )

    row_a = db.execute(
        queries.BOTTLE_BY_ID, {"bottle_id": bottle_a},
    ).mappings().first()
    if row_a is None:
        raise HTTPException(status_code=404, detail=f"Bottle {bottle_a} not found")

    row_b = db.execute(
        queries.BOTTLE_BY_ID, {"bottle_id": bottle_b},
    ).mappings().first()
    if row_b is None:
        raise HTTPException(status_code=404, detail=f"Bottle {bottle_b} not found")

    result = flavor_breakdown(
        row_a["flavor_profile"],
        row_b["flavor_profile"],
        gustative_weight=gustative_weight,
        structural_weight=structural_weight,
    )

    return {
        "bottle_a": {
            "id": row_a["id"],
            "brand": row_a["brand"],
            "label": row_a["label"],
            "class_name": row_a["class_name"],
        },
        "bottle_b": {
            "id": row_b["id"],
            "brand": row_b["brand"],
            "label": row_b["label"],
            "class_name": row_b["class_name"],
        },
        "total_distance": result.total_distance,
        "gustative_distance": result.gustative_distance,
        "structural_distance": result.structural_distance,
        "weights": result.weights,
        "per_dimension": [d.model_dump() for d in result.per_dimension],
    }


@router.get("/flavor/similar-bottles")
def similar_bottles(
    bottle_id: int = Query(...),
    top: int = Query(10, ge=1, le=50),
    max_distance: float | None = Query(None),
    same_family_only: bool = Query(False),
    db: Session = Depends(get_db),
):
    result = compute_similar_bottles(
        db,
        bottle_id,
        top=top,
        max_distance=max_distance,
        same_family_only=same_family_only,
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f"Bottle {bottle_id} not found")
    return result


@router.get("/flavor/substitution-trace")
def substitution_trace(
    recipe_id: int = Query(...),
    recipe_ingredient_id: int = Query(...),
    db: Session = Depends(get_db),
):
    result = compute_substitution_trace(db, recipe_id, recipe_ingredient_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Recipe or recipe_ingredient not found",
        )
    return result
