"""Shared inventory helpers."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


def get_on_hand_class_ids(session: Session) -> set[int]:
    """Return the set of class_ids for which at least one bottle is on_hand."""
    rows = session.execute(
        text("SELECT DISTINCT class_id FROM bottle WHERE on_hand = TRUE")
    ).all()
    return {r[0] for r in rows}
