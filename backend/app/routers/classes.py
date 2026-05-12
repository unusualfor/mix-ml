from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ClassFlat, ClassNode
from app import queries

router = APIRouter(tags=["classes"])


def _build_tree(rows: list[dict]) -> list[ClassNode]:
    nodes: dict[int, ClassNode] = {}
    roots: list[ClassNode] = []

    for r in rows:
        nodes[r["id"]] = ClassNode(
            id=r["id"], name=r["name"], is_garnish=r["is_garnish"],
            is_commodity=r["is_commodity"],
        )

    for r in rows:
        node = nodes[r["id"]]
        parent_id = r["parent_id"]
        if parent_id is None:
            roots.append(node)
        elif parent_id in nodes:
            nodes[parent_id].children.append(node)

    return roots


@router.get("/classes")
def list_classes(
    flat: bool = Query(False),
    db: Session = Depends(get_db),
) -> list[ClassFlat] | list[ClassNode]:
    rows = [dict(r) for r in db.execute(queries.ALL_CLASSES).mappings().all()]

    if flat:
        return [ClassFlat(**r) for r in rows]

    return _build_tree(rows)
