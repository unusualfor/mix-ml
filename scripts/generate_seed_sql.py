#!/usr/bin/env python3
"""
Generate a Postgres 16+ seed SQL file from normalized IBA cocktails JSON.

Usage:
    python generate_seed_sql.py iba_cocktails_normalized.json

Produces:
    seed.sql — DDL + INSERT statements ready for psql -f seed.sql
"""

import csv
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Hierarchy of ingredient classes (parent → children)
# ---------------------------------------------------------------------------
HIERARCHY: dict[str, list[str]] = {
    "Whiskey": [
        "Bourbon (generic)", "Wheated Bourbon", "Rye Whiskey",
        "Irish Whiskey", "Blended Scotch", "Single Malt Scotch (peated)",
    ],
    "Gin": [
        "Gin (generic)", "London Dry Gin", "Old Tom Gin",
        "Japanese Gin", "Botanical Gin",
    ],
    "Rum": [
        "Rum (generic)", "White Rum", "Aged Rum", "Demerara Rum",
        "Blackstrap Rum", "Cuban White Rum", "Cuban Aged Rum",
        "Cuban Aguardiente", "Jamaican Aged Rum", "Jamaican Dark Rum",
        "Jamaican Overproof Rum", "Bermuda Dark Rum",
        "Puerto Rican Aged Rum", "Rhum Agricole",
    ],
    "Vodka": ["Vodka (generic)", "Citron Vodka", "Vanilla Vodka"],
    "Agave Spirit": ["Tequila Blanco", "Mezcal", "Mezcal Espadín"],
    "Brandy": [
        "Brandy (generic)", "Cognac", "Calvados", "Pisco", "Cachaça",
        "Grappa", "Apricot Brandy", "Peach Brandy", "Greek Brandy",
    ],
    "Wine-Based Aperitif": [
        "Vermouth Rosso", "Vermouth Bianco", "Vermouth Dry",
        "Vermouth Amaro", "Lillet Blanc",
        "Amontillado Sherry", "Palo Cortado",
        "Red Tawny Port",
    ],
    "Wine": [
        "Dry White Wine", "Red Wine", "Champagne", "Prosecco",
        "Sparkling Wine (generic)",
    ],
    "Bitter Italiano": [
        "Campari", "Aperol", "Select",
        "Bitter Italiano Generico",
    ],
    "Aromatic Bitters": [
        "Angostura Aromatic Bitters", "Orange Bitters",
        "Peychaud's Aromatic Bitters",
    ],
    "Amaro": [
        "Amaro Nonino", "Amaro Montenegro", "Amaro Formidabile",
        "Amaro Alpino", "Cynar", "Fernet (generic)", "Fernet Branca",
    ],
    "Liqueur": [
        "Triple Sec", "Cointreau", "Grand Marnier", "Orange Curaçao",
        "Maraschino", "Sangue Morlacco",
        "Crème de Cassis", "Crème de Cacao Brown", "Crème de Cacao White",
        "Crème de Menthe Green", "Crème de Menthe White",
        "Crème de Mûre", "Crème de Violette",
        "Bénédictine", "Chartreuse Yellow", "Chartreuse Green",
        "Drambuie", "Absinthe", "Pastis", "Tintura Imperiale",
        "Allspice Dram",
        "Coffee Liqueur (generic)", "Kahlúa",
        "Amaretto", "Frangelico",
        "Falernum", "Chandolia Mastiha",
        "Passion Fruit Liqueur", "Raspberry Liqueur",
        "Elderflower Cordial", "Chamomile Cordial", "Peach Schnapps",
    ],
    "Sake & Umeshu": [
        "Sake Junmai Daiginjo", "Sake (generic)", "Umeshu Premium",
    ],
    "Juice": [
        "Fresh Lemon Juice", "Fresh Lime Juice", "Fresh Orange Juice",
        "Fresh Pineapple Juice", "Fresh Grapefruit Juice",
        "Cranberry Juice", "Tomato Juice", "Sugar Cane Juice",
        "Passion Fruit Purée",
    ],
    "Syrup & Sweetener": [
        "Simple Syrup", "Demerara Syrup", "Honey Syrup",
        "Honey Mix", "Honey-Chamomile Mix", "Grenadine",
        "Orgeat", "Raspberry Syrup", "Passion Fruit Syrup",
        "White Peach Purée", "Sugar", "Sugar Cube",
        "Fine Sugar", "Cane Sugar", "Demerara Sugar",
        "Vanilla Sugar", "Agave Nectar", "Raw Honey",
    ],
    "Mixer": [
        "Soda Water", "Ginger Beer", "Ginger Ale", "Cola",
        "Tonic Water", "Pink Grapefruit Soda",
    ],
    "Dairy & Egg": ["Egg White", "Egg Yolk", "Cream", "Coconut Cream"],
    "Misc": [
        "Espresso", "Hot Coffee", "Salt", "Cloves", "Vanilla Extract",
        "Orange Flower Water", "Worcestershire Sauce",
        "Seasoning Mix (Bloody Mary)", "Donn's Mix", "Water",
    ],
}

GARNISH_CHILDREN: list[str] = [
    "Lemon Wheel", "Orange Wheel", "Lemon Zest", "Mint Sprig",
    "Mint Leaves", "Basil Leaves", "Lime Wedges",
    "Chili Pepper Slices", "Pineapple Chunks", "Ginger Slice",
]

# ---------------------------------------------------------------------------
# Commodity classes (always-available pantry/fridge items)
# ---------------------------------------------------------------------------
COMMODITY_NAMES: set[str] = {
    # Carbonated mixers
    "Soda Water", "Tonic Water", "Ginger Beer", "Ginger Ale",
    "Cola", "Pink Grapefruit Soda",
    # Fresh juices
    "Fresh Lemon Juice", "Fresh Lime Juice", "Fresh Orange Juice",
    "Fresh Pineapple Juice", "Fresh Grapefruit Juice",
    "Cranberry Juice", "Tomato Juice", "Sugar Cane Juice",
    # Sugars
    "Sugar", "Sugar Cube", "Fine Sugar", "Cane Sugar",
    "Demerara Sugar", "Vanilla Sugar",
    # Simple syrups
    "Simple Syrup", "Honey Syrup", "Honey Mix", "Raw Honey",
    # Dairy & eggs
    "Egg White", "Egg Yolk", "Cream", "Coconut Cream",
    # Pantry staples
    "Salt", "Cloves", "Vanilla Extract", "Water", "Worcestershire Sauce",
    # Coffee
    "Hot Coffee", "Espresso",
}

# ---------------------------------------------------------------------------
# Bottles — loaded from scripts/data/bottles_seed.json
# ---------------------------------------------------------------------------
_bottles_path = Path(__file__).parent / "data" / "bottles_seed.json"
if _bottles_path.exists():
    with open(_bottles_path, encoding="utf-8") as _f:
        BOTTLES: list[dict] = [
            {
                "class": b["class_name"],
                "brand": b["brand"],
                "label": b.get("label"),
                "abv": b.get("abv"),
                "flavor": b.get("flavor_profile", {}),
            }
            for b in json.load(_f)
        ]
else:
    BOTTLES: list[dict] = []

# ---------------------------------------------------------------------------
# Glass extraction patterns (order matters — first match wins)
# ---------------------------------------------------------------------------
GLASS_PATTERNS: list[tuple[str, str]] = [
    (r"old.?fashioned\s+glass", "old fashioned"),
    (r"highball", "highball"),
    (r"rocks\s+glass", "rocks"),
    (r"collins", "collins"),
    (r"champagne\s+flute", "flute"),
    (r"\bflute\b", "flute"),
    (r"coupe", "coupe"),
    (r"cocktail\s+glass", "cocktail"),
    (r"wine\s+glass", "wine"),
    (r"hurricane", "hurricane"),
    (r"shot\s+glass", "shot"),
    (r"tumbler", "tumbler"),
]

# ---------------------------------------------------------------------------
# SQL helpers
# ---------------------------------------------------------------------------

def sql_str(value: str | None) -> str:
    """Escape a Python string for SQL literal, or return NULL."""
    if value is None:
        return "NULL"
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def sql_num(value) -> str:
    """Format a numeric value for SQL, or NULL."""
    if value is None:
        return "NULL"
    if isinstance(value, float):
        if value == int(value):
            return str(int(value))
        return str(value)
    return str(value)


def sql_bool(value: bool) -> str:
    return "TRUE" if value else "FALSE"


def sql_jsonb(obj: dict) -> str:
    """Render a Python dict as a SQL JSONB literal."""
    return sql_str(json.dumps(obj, ensure_ascii=False))


def class_subquery(name: str) -> str:
    """Generate (SELECT id FROM ingredient_class WHERE name = '...')."""
    return f"(SELECT id FROM ingredient_class WHERE name = {sql_str(name)})"


def recipe_subquery(name: str) -> str:
    """Generate (SELECT id FROM recipe WHERE name = '...')."""
    return f"(SELECT id FROM recipe WHERE name = {sql_str(name)})"


# ---------------------------------------------------------------------------
# Glass extraction
# ---------------------------------------------------------------------------

def extract_glass(method: str | None) -> str | None:
    if not method:
        return None
    for pattern, glass in GLASS_PATTERNS:
        if re.search(pattern, method, re.IGNORECASE):
            return glass
    return None


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

DDL = """\
-- ==========================================================================
-- IBA Cocktail Database — Seed SQL
-- Generated by generate_seed_sql.py
-- ==========================================================================

-- DDL
-- --------------------------------------------------------------------------

DROP TABLE IF EXISTS recipe_ingredient CASCADE;
DROP TABLE IF EXISTS bottle CASCADE;
DROP TABLE IF EXISTS recipe CASCADE;
DROP TABLE IF EXISTS ingredient_class CASCADE;

CREATE TABLE ingredient_class (
    id           SERIAL PRIMARY KEY,
    parent_id    INT REFERENCES ingredient_class(id),
    name         TEXT NOT NULL UNIQUE,
    is_garnish   BOOLEAN NOT NULL DEFAULT FALSE,
    is_commodity BOOLEAN NOT NULL DEFAULT FALSE,
    notes        TEXT
);

CREATE TABLE bottle (
    id              SERIAL PRIMARY KEY,
    class_id        INT NOT NULL REFERENCES ingredient_class(id),
    brand           TEXT NOT NULL,
    label           TEXT,
    abv             NUMERIC(4,1),
    on_hand         BOOLEAN NOT NULL DEFAULT TRUE,
    flavor_profile  JSONB NOT NULL,
    notes           TEXT,
    added_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE recipe (
    id            SERIAL PRIMARY KEY,
    name          TEXT NOT NULL UNIQUE,
    iba_category  TEXT NOT NULL CHECK (iba_category IN
                   ('unforgettable','contemporary','new_era')),
    method        TEXT NOT NULL,
    glass         TEXT,
    garnish       TEXT,
    source_url    TEXT
);

CREATE TABLE recipe_ingredient (
    id                    SERIAL PRIMARY KEY,
    recipe_id             INT NOT NULL REFERENCES recipe(id) ON DELETE CASCADE,
    class_id              INT NOT NULL REFERENCES ingredient_class(id),
    amount                NUMERIC(7,2),
    unit                  TEXT,
    is_optional           BOOLEAN NOT NULL DEFAULT FALSE,
    is_garnish            BOOLEAN NOT NULL DEFAULT FALSE,
    alternative_group_id  INT,
    raw_name              TEXT,
    notes                 TEXT
);

CREATE INDEX idx_recipe_ing_recipe ON recipe_ingredient(recipe_id);
CREATE INDEX idx_recipe_ing_class ON recipe_ingredient(class_id);
CREATE INDEX idx_recipe_ing_alt ON recipe_ingredient(alternative_group_id);
CREATE INDEX idx_bottle_class ON bottle(class_id);
"""


def generate(recipes: list[dict]) -> str:
    lines: list[str] = [DDL]

    # Collect all known classes (from hierarchy + garnish)
    all_parents: list[str] = list(HIERARCHY.keys()) + ["Garnish"]
    # Build child→parent lookup
    child_to_parent: dict[str, str] = {}
    for parent, children in HIERARCHY.items():
        for child in children:
            child_to_parent[child] = parent
    for g in GARNISH_CHILDREN:
        child_to_parent[g] = "Garnish"

    all_known: set[str] = set(all_parents) | set(child_to_parent.keys())

    # Collect all classes referenced in recipes
    recipe_classes: set[str] = set()
    for recipe in recipes:
        for ing in recipe.get("ingredients", []):
            cls = ing.get("class")
            if isinstance(cls, list):
                recipe_classes.update(cls)
            elif isinstance(cls, str):
                recipe_classes.add(cls)

    # Warn about unmapped classes
    unmapped: set[str] = set()
    for cls in recipe_classes:
        if cls not in all_known:
            unmapped.add(cls)
            print(f"WARNING: class '{cls}' not in HIERARCHY — will be skipped")

    # ------------------------------------------------------------------
    # 1. ingredient_class — root parents
    # ------------------------------------------------------------------
    lines.append("")
    lines.append("-- ==========================================================================")
    lines.append("-- ingredient_class — root parents")
    lines.append("-- ==========================================================================")
    lines.append("")

    for parent_name in all_parents:
        is_g = sql_bool(parent_name == "Garnish")
        lines.append(
            f"INSERT INTO ingredient_class (name, parent_id, is_garnish, is_commodity) "
            f"VALUES ({sql_str(parent_name)}, NULL, {is_g}, FALSE);"
        )

    # ------------------------------------------------------------------
    # 2. ingredient_class — leaf children
    # ------------------------------------------------------------------
    lines.append("")
    lines.append("-- ==========================================================================")
    lines.append("-- ingredient_class — leaf children")
    lines.append("-- ==========================================================================")

    count_leaf = 0
    for parent_name in list(HIERARCHY.keys()):
        children = HIERARCHY[parent_name]
        lines.append("")
        lines.append(f"-- {parent_name}")
        for child in children:
            is_g = sql_bool(False)
            is_c = sql_bool(child in COMMODITY_NAMES)
            lines.append(
                f"INSERT INTO ingredient_class (name, parent_id, is_garnish, is_commodity) "
                f"VALUES ({sql_str(child)}, {class_subquery(parent_name)}, {is_g}, {is_c});"
            )
            count_leaf += 1

    # Garnish children
    lines.append("")
    lines.append("-- Garnish")
    for child in GARNISH_CHILDREN:
        lines.append(
            f"INSERT INTO ingredient_class (name, parent_id, is_garnish, is_commodity) "
            f"VALUES ({sql_str(child)}, {class_subquery('Garnish')}, TRUE, FALSE);"
        )
        count_leaf += 1

    total_classes = len(all_parents) + count_leaf

    # ------------------------------------------------------------------
    # 3. recipe
    # ------------------------------------------------------------------
    lines.append("")
    lines.append("-- ==========================================================================")
    lines.append("-- recipe")
    lines.append("-- ==========================================================================")
    lines.append("")

    for i, recipe in enumerate(recipes):
        name = recipe["name"]
        iba_cat = recipe.get("iba_category", "contemporary")
        method = recipe.get("method") or ""
        garnish = recipe.get("garnish")
        source_url = recipe.get("source_url")
        glass = extract_glass(method)

        lines.append(
            f"INSERT INTO recipe (name, iba_category, method, glass, garnish, source_url) "
            f"VALUES ({sql_str(name)}, {sql_str(iba_cat)}, {sql_str(method)}, "
            f"{sql_str(glass)}, {sql_str(garnish)}, {sql_str(source_url)});"
        )
        if (i + 1) % 20 == 0:
            lines.append(f"-- ({i + 1} recipes inserted)")

    lines.append(f"-- ({len(recipes)} recipes total)")

    # ------------------------------------------------------------------
    # 4. recipe_ingredient
    # ------------------------------------------------------------------
    lines.append("")
    lines.append("-- ==========================================================================")
    lines.append("-- recipe_ingredient")
    lines.append("-- ==========================================================================")
    lines.append("")

    alt_group_id = 0
    ri_count = 0
    skipped_count = 0
    garnish_count = 0
    alt_group_count = 0

    for recipe in recipes:
        recipe_name = recipe["name"]
        ingredients = recipe.get("ingredients", [])
        if not ingredients:
            lines.append(f"-- {recipe_name}: no ingredients")
            continue

        lines.append(f"-- {recipe_name}")
        for ing in ingredients:
            cls = ing.get("class")
            amount = ing.get("amount")
            unit = ing.get("unit")
            is_optional = ing.get("is_optional", False)
            is_garnish = ing.get("is_garnish", False)
            raw_name = ing.get("raw_name")
            notes = ing.get("notes")

            if is_garnish:
                garnish_count += 1

            if isinstance(cls, list):
                # Alternative group — generate one row per alternative
                alt_group_id += 1
                alt_group_count += 1
                for alt_cls in cls:
                    if alt_cls in unmapped:
                        lines.append(
                            f"-- SKIPPED unmapped: {alt_cls} "
                            f"(recipe: {recipe_name}, raw: {raw_name})"
                        )
                        skipped_count += 1
                        continue
                    lines.append(
                        f"INSERT INTO recipe_ingredient "
                        f"(recipe_id, class_id, amount, unit, is_optional, "
                        f"is_garnish, alternative_group_id, raw_name, notes) "
                        f"VALUES ({recipe_subquery(recipe_name)}, "
                        f"{class_subquery(alt_cls)}, "
                        f"{sql_num(amount)}, {sql_str(unit)}, "
                        f"{sql_bool(is_optional)}, {sql_bool(is_garnish)}, "
                        f"{alt_group_id}, {sql_str(raw_name)}, {sql_str(notes)});"
                    )
                    ri_count += 1
            elif isinstance(cls, str):
                if cls in unmapped:
                    lines.append(
                        f"-- SKIPPED unmapped: {cls} "
                        f"(recipe: {recipe_name}, raw: {raw_name})"
                    )
                    skipped_count += 1
                    continue
                lines.append(
                    f"INSERT INTO recipe_ingredient "
                    f"(recipe_id, class_id, amount, unit, is_optional, "
                    f"is_garnish, alternative_group_id, raw_name, notes) "
                    f"VALUES ({recipe_subquery(recipe_name)}, "
                    f"{class_subquery(cls)}, "
                    f"{sql_num(amount)}, {sql_str(unit)}, "
                    f"{sql_bool(is_optional)}, {sql_bool(is_garnish)}, "
                    f"NULL, {sql_str(raw_name)}, {sql_str(notes)});"
                )
                ri_count += 1
            else:
                lines.append(
                    f"-- SKIPPED: no class for ingredient "
                    f"(recipe: {recipe_name}, raw: {raw_name})"
                )
                skipped_count += 1

    lines.append(f"-- ({ri_count} recipe_ingredient rows total)")

    # ------------------------------------------------------------------
    # 5. bottle
    # ------------------------------------------------------------------
    lines.append("")
    lines.append("-- ==========================================================================")
    lines.append("-- bottle (Francesco's collection)")
    lines.append("-- ==========================================================================")
    lines.append("")

    if not BOTTLES:
        lines.append("-- No bottles defined yet — populate BOTTLES in the script.")
    else:
        for i, bot in enumerate(BOTTLES):
            cls_name = bot["class"]
            brand = bot["brand"]
            label = bot.get("label")
            abv = bot.get("abv")
            flavor = bot.get("flavor", {})
            lines.append(
                f"INSERT INTO bottle (class_id, brand, label, abv, flavor_profile) "
                f"VALUES ({class_subquery(cls_name)}, {sql_str(brand)}, "
                f"{sql_str(label)}, {sql_num(abv)}, {sql_jsonb(flavor)});"
            )
            if (i + 1) % 10 == 0:
                lines.append(f"-- ({i + 1} bottles inserted)")
        lines.append(f"-- ({len(BOTTLES)} bottles total)")

    lines.append("")
    lines.append("-- ==========================================================================")
    lines.append("-- Seed complete")
    lines.append("-- ==========================================================================")

    # Summary to stdout
    print()
    print("=" * 60)
    print("  SEED SQL GENERATION SUMMARY")
    print("=" * 60)
    print(f"  ingredient_class : {total_classes} "
          f"({len(all_parents)} parents + {count_leaf} children)")
    print(f"  recipe           : {len(recipes)}")
    print(f"  recipe_ingredient: {ri_count}")
    print(f"  alternative_groups: {alt_group_count}")
    print(f"  garnish entries  : {garnish_count}")
    print(f"  bottles          : {len(BOTTLES)}")
    print(f"  skipped (unmapped): {skipped_count}")
    print("=" * 60)

    return "\n".join(lines) + "\n"


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python generate_seed_sql.py <iba_cocktails_normalized.json>")
        sys.exit(1)

    input_path = sys.argv[1]
    if not Path(input_path).exists():
        print(f"Error: file not found: {input_path}")
        sys.exit(1)

    print(f"Loading {input_path}...")
    with open(input_path, encoding="utf-8") as f:
        recipes = json.load(f)
    print(f"Loaded {len(recipes)} recipes.")

    sql = generate(recipes)

    out_path = Path("seed.sql")
    out_path.write_text(sql, encoding="utf-8")
    print(f"\nOutput → {out_path.resolve()}")


if __name__ == "__main__":
    main()
