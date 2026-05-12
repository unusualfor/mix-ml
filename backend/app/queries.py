"""Centralised SQL queries — raw text with bound parameters."""

from sqlalchemy import text

# ---------------------------------------------------------------------------
# ingredient_class
# ---------------------------------------------------------------------------

ALL_CLASSES = text("""
    SELECT id, parent_id, name, is_garnish, is_commodity
    FROM ingredient_class
    ORDER BY parent_id NULLS FIRST, name
""")

# ---------------------------------------------------------------------------
# recipe — list
# ---------------------------------------------------------------------------

RECIPES_LIST = text("""
    SELECT r.id, r.name, r.iba_category, r.glass,
           COUNT(ri.id) AS ingredient_count
    FROM recipe r
    LEFT JOIN recipe_ingredient ri ON ri.recipe_id = r.id
    WHERE (CAST(:category AS text) IS NULL OR r.iba_category = :category)
      AND (CAST(:search AS text) IS NULL OR r.name ILIKE :search)
    GROUP BY r.id, r.name, r.iba_category, r.glass
    ORDER BY r.name
    LIMIT :limit OFFSET :offset
""")

RECIPES_COUNT = text("""
    SELECT COUNT(*) FROM recipe
    WHERE (CAST(:category AS text) IS NULL OR iba_category = :category)
      AND (CAST(:search AS text) IS NULL OR name ILIKE :search)
""")

# ---------------------------------------------------------------------------
# recipe — single
# ---------------------------------------------------------------------------

RECIPE_BY_ID = text("""
    SELECT id, name, iba_category, method, glass, garnish, source_url
    FROM recipe
    WHERE id = :recipe_id
""")

RECIPE_BY_NAME = text("""
    SELECT id, name, iba_category, method, glass, garnish, source_url
    FROM recipe
    WHERE LOWER(name) = LOWER(:name)
""")

RECIPE_INGREDIENTS = text("""
    SELECT ri.class_id,
           ic.name AS class_name,
           ri.amount,
           ri.unit,
           ri.is_optional,
           ri.is_garnish,
           ri.alternative_group_id,
           ri.raw_name
    FROM recipe_ingredient ri
    JOIN ingredient_class ic ON ic.id = ri.class_id
    WHERE ri.recipe_id = :recipe_id
    ORDER BY ri.id
""")

# ---------------------------------------------------------------------------
# bottle
# ---------------------------------------------------------------------------

CLASS_BY_NAME = text("""
    SELECT id FROM ingredient_class WHERE name = :name
""")

INSERT_BOTTLE = text("""
    INSERT INTO bottle (class_id, brand, label, abv, on_hand, flavor_profile, notes)
    VALUES (:class_id, :brand, :label, :abv, :on_hand, :flavor_profile, :notes)
    RETURNING id, class_id, brand, label, abv, on_hand, flavor_profile, notes, added_at
""")

FIND_BOTTLE_BY_BRAND_LABEL = text("""
    SELECT id FROM bottle WHERE brand = :brand AND COALESCE(label, '') = COALESCE(:label, '')
""")

UPDATE_BOTTLE_FULL = text("""
    UPDATE bottle SET class_id = :class_id, abv = :abv, on_hand = :on_hand,
           flavor_profile = CAST(:flavor_profile AS jsonb), notes = :notes,
           label = :label
    WHERE id = :bottle_id
    RETURNING id
""")

BOTTLE_BY_ID = text("""
    SELECT b.id, b.class_id, ic.name AS class_name,
           p.name AS family_name,
           b.brand, b.label, b.abv, b.on_hand,
           b.flavor_profile, b.notes, b.added_at
    FROM bottle b
    JOIN ingredient_class ic ON ic.id = b.class_id
    LEFT JOIN ingredient_class p ON p.id = ic.parent_id
    WHERE b.id = :bottle_id
""")

BOTTLES_LIST = text("""
    SELECT b.id, b.class_id, ic.name AS class_name,
           p.name AS family_name,
           b.brand, b.label, b.abv, b.on_hand,
           b.flavor_profile, b.notes, b.added_at
    FROM bottle b
    JOIN ingredient_class ic ON ic.id = b.class_id
    LEFT JOIN ingredient_class p ON p.id = ic.parent_id
    WHERE (CAST(:on_hand AS text) IS NULL OR b.on_hand = CAST(:on_hand AS boolean))
      AND (CAST(:class_name AS text) IS NULL OR ic.name = :class_name)
      AND (CAST(:family AS text) IS NULL OR p.name = :family)
    ORDER BY ic.name, b.brand
    LIMIT :limit OFFSET :offset
""")

BOTTLES_COUNT = text("""
    SELECT COUNT(*)
    FROM bottle b
    JOIN ingredient_class ic ON ic.id = b.class_id
    LEFT JOIN ingredient_class p ON p.id = ic.parent_id
    WHERE (CAST(:on_hand AS text) IS NULL OR b.on_hand = CAST(:on_hand AS boolean))
      AND (CAST(:class_name AS text) IS NULL OR ic.name = :class_name)
      AND (CAST(:family AS text) IS NULL OR p.name = :family)
""")

DELETE_BOTTLE = text("""
    DELETE FROM bottle WHERE id = :bottle_id RETURNING id
""")

# ---------------------------------------------------------------------------
# feasibility (can-make-now)
# ---------------------------------------------------------------------------

REQUIRED_INGREDIENTS = text("""
    SELECT ri.id, ri.recipe_id, ri.class_id, ri.alternative_group_id
    FROM recipe_ingredient ri
    JOIN ingredient_class ic ON ic.id = ri.class_id
    WHERE ri.is_optional = FALSE AND ri.is_garnish = FALSE
      AND ic.is_commodity = FALSE
""")

RECIPE_INGREDIENTS_FULL = text("""
    SELECT ri.id, ri.recipe_id, ri.class_id, ic.name AS class_name,
           ri.is_optional, ri.is_garnish, ri.alternative_group_id,
           ic.is_commodity
    FROM recipe_ingredient ri
    JOIN ingredient_class ic ON ic.id = ri.class_id
    WHERE ri.recipe_id = :recipe_id
    ORDER BY ri.id
""")

ON_HAND_BOTTLES_FOR_CLASS = text("""
    SELECT b.id, b.brand, b.label
    FROM bottle b
    WHERE b.on_hand = TRUE AND b.class_id = :class_id
""")

ON_HAND_BOTTLES_FOR_SIBLINGS = text("""
    SELECT b.id, b.brand, b.label
    FROM bottle b
    JOIN ingredient_class ic ON ic.id = b.class_id
    WHERE b.on_hand = TRUE
      AND ic.parent_id = (SELECT parent_id FROM ingredient_class WHERE id = :class_id)
""")

ALL_RECIPES_BRIEF = text("""
    SELECT id, name, iba_category, glass FROM recipe ORDER BY name
""")

# ---------------------------------------------------------------------------
# optimizer (optimize-next)
# ---------------------------------------------------------------------------

CANDIDATE_CLASSES = text("""
    SELECT ic.id, ic.name, ic.parent_id, p.name AS parent_family
    FROM ingredient_class ic
    LEFT JOIN ingredient_class p ON p.id = ic.parent_id
    WHERE ic.parent_id IS NOT NULL
      AND ic.is_commodity = FALSE
      AND ic.is_garnish = FALSE
      AND (
          -- Rule 1: class appears directly in a recipe ingredient
          EXISTS (
              SELECT 1 FROM recipe_ingredient ri WHERE ri.class_id = ic.id
          )
          OR
          -- Rule 2: class is sibling of a "(generic)" class used in a recipe
          -- (buying this specific class satisfies the generic requirement)
          EXISTS (
              SELECT 1
              FROM ingredient_class gen
              JOIN recipe_ingredient ri ON ri.class_id = gen.id
              WHERE gen.parent_id = ic.parent_id
                AND gen.name LIKE '%% (generic)'
          )
      )
    ORDER BY ic.name
""")

# ---------------------------------------------------------------------------
# flavor / substitution
# ---------------------------------------------------------------------------

ALL_BOTTLES_WITH_PROFILE = text("""
    SELECT b.id, b.class_id, ic.name AS class_name,
           ic.parent_id, p.name AS family_name,
           b.brand, b.label, b.on_hand, b.flavor_profile
    FROM bottle b
    JOIN ingredient_class ic ON ic.id = b.class_id
    LEFT JOIN ingredient_class p ON p.id = ic.parent_id
    ORDER BY ic.name, b.brand
""")

RECIPE_INGREDIENTS_FOR_SUBSTITUTION = text("""
    SELECT ri.id AS recipe_ingredient_id, ri.class_id,
           ic.name AS class_name, ic.parent_id,
           p.name AS parent_family,
           ri.amount, ri.unit,
           ri.is_optional, ri.is_garnish, ic.is_commodity,
           ri.alternative_group_id
    FROM recipe_ingredient ri
    JOIN ingredient_class ic ON ic.id = ri.class_id
    LEFT JOIN ingredient_class p ON p.id = ic.parent_id
    WHERE ri.recipe_id = :recipe_id
    ORDER BY ri.id
""")
