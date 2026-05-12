from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import (
    CanMakeItem,
    CanMakeResponse,
    CanMakeSummary,
    FeasibilityIngredient,
    FeasibilityResponse,
    RecipeListItem,
    SatisfyingBottle,
)
from app import queries
from app.services.feasibility import (
    compute_feasibility,
    compute_single_recipe_feasibility,
    _on_hand_class_ids_from_db,
    _build_class_hierarchy,
)

router = APIRouter(tags=["cocktails"])

CanMakeStatus = Literal["can_make", "cannot_make", "all"]


@router.get("/cocktails/can-make-now", response_model=CanMakeResponse)
def can_make_now(
    status: CanMakeStatus = Query("can_make"),
    max_missing: int | None = Query(None, ge=0),
    category: str | None = Query(None),
    db: Session = Depends(get_db),
):
    on_hand = _on_hand_class_ids_from_db(db)
    feasibility = compute_feasibility(db, on_hand)

    # Fetch recipe metadata
    recipe_rows = db.execute(queries.ALL_RECIPES_BRIEF).mappings().all()
    recipe_map = {r["id"]: dict(r) for r in recipe_rows}

    items: list[CanMakeItem] = []
    total_can = 0
    total_cannot = 0

    for rid, result in feasibility.items():
        recipe = recipe_map.get(rid)
        if recipe is None:
            continue
        if category and recipe["iba_category"] != category:
            continue

        if result.can_make:
            total_can += 1
        else:
            total_cannot += 1

        # Filter by requested status
        if status == "can_make" and not result.can_make:
            continue
        if status == "cannot_make" and result.can_make:
            continue
        if status == "cannot_make" and max_missing is not None:
            if result.missing_count > max_missing:
                continue

        items.append(CanMakeItem(
            id=recipe["id"],
            name=recipe["name"],
            iba_category=recipe["iba_category"],
            glass=recipe["glass"],
            can_make=result.can_make,
            missing_count=result.missing_count,
            missing_classes=result.missing_classes,
        ))

    items.sort(key=lambda x: x.name)

    total_recipes = total_can + total_cannot

    return CanMakeResponse(
        summary=CanMakeSummary(
            total_recipes=total_recipes,
            can_make=total_can,
            cannot_make=total_cannot,
            on_hand_classes=len(on_hand),
        ),
        items=items,
    )


@router.get("/cocktails/{recipe_id}/feasibility", response_model=FeasibilityResponse)
def recipe_feasibility(recipe_id: int, db: Session = Depends(get_db)):
    # Get recipe metadata
    recipe_row = db.execute(
        queries.RECIPE_BY_ID, {"recipe_id": recipe_id},
    ).mappings().first()
    if recipe_row is None:
        raise HTTPException(status_code=404, detail="Recipe not found")

    recipe_data = dict(recipe_row)
    on_hand = _on_hand_class_ids_from_db(db)
    hierarchy = _build_class_hierarchy(db)

    result = compute_single_recipe_feasibility(db, recipe_id, on_hand)

    # Build detailed ingredient list
    ing_rows = db.execute(
        queries.RECIPE_INGREDIENTS_FULL, {"recipe_id": recipe_id},
    ).mappings().all()

    ingredients: list[FeasibilityIngredient] = []
    for ing in ing_rows:
        class_id = ing["class_id"]
        class_name = ing["class_name"]
        # For generic classes, find bottles from any sibling class
        if class_id in hierarchy["generic_ids"]:
            bottles = db.execute(
                queries.ON_HAND_BOTTLES_FOR_SIBLINGS, {"class_id": class_id},
            ).mappings().all()
        else:
            bottles = db.execute(
                queries.ON_HAND_BOTTLES_FOR_CLASS, {"class_id": class_id},
            ).mappings().all()
        ingredients.append(FeasibilityIngredient(
            class_name=ing["class_name"],
            satisfied_by_bottles=[SatisfyingBottle(**dict(b)) for b in bottles],
            is_optional=ing["is_optional"],
            is_garnish=ing["is_garnish"],
            is_commodity=ing["is_commodity"],
            alternative_group_id=ing["alternative_group_id"],
        ))

    # Count ingredients for RecipeListItem
    ing_count = len(ing_rows)

    return FeasibilityResponse(
        recipe=RecipeListItem(
            id=recipe_data["id"],
            name=recipe_data["name"],
            iba_category=recipe_data["iba_category"],
            glass=recipe_data["glass"],
            ingredient_count=ing_count,
        ),
        can_make=result.can_make,
        ingredients=ingredients,
    )
