from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import IngredientDetail, RecipeDetail, RecipeListResponse
from app import queries

router = APIRouter(tags=["recipes"])

IbaCategory = Literal["unforgettable", "contemporary", "new_era"]


def _recipe_detail(db: Session, row: dict) -> RecipeDetail:
    ingredients = db.execute(
        queries.RECIPE_INGREDIENTS, {"recipe_id": row["id"]},
    ).mappings().all()
    return RecipeDetail(
        **row,
        ingredients=[IngredientDetail(**dict(i)) for i in ingredients],
    )


@router.get("/recipes", response_model=RecipeListResponse)
def list_recipes(
    category: IbaCategory | None = Query(None),
    search: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    search_pattern = f"%{search}%" if search else None

    params = {
        "category": category,
        "search": search_pattern,
        "limit": limit,
        "offset": offset,
    }

    total = db.execute(queries.RECIPES_COUNT, params).scalar_one()
    rows = db.execute(queries.RECIPES_LIST, params).mappings().all()

    return RecipeListResponse(
        total=total,
        items=[dict(r) for r in rows],
    )


@router.get("/recipes/by-name", response_model=RecipeDetail)
def get_recipe_by_name(
    name: str = Query(...),
    db: Session = Depends(get_db),
):
    row = db.execute(
        queries.RECIPE_BY_NAME, {"name": name},
    ).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return _recipe_detail(db, dict(row))


@router.get("/recipes/{recipe_id}", response_model=RecipeDetail)
def get_recipe(recipe_id: int, db: Session = Depends(get_db)):
    row = db.execute(
        queries.RECIPE_BY_ID, {"recipe_id": recipe_id},
    ).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return _recipe_detail(db, dict(row))
