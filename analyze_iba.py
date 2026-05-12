#!/usr/bin/env python3
"""
Descriptive analysis of IBA cocktails JSON.

Produces 5 report files:
  1. report_ingredient_frequency.csv
  2. report_unit_inventory.csv
  3. report_amount_anomalies.txt
  4. report_ingredient_clusters.txt
  5. report_summary.md

Usage:
    python analyze_iba.py iba_cocktails.json
"""

import csv
import difflib
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_data(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_csv(path: str, header: list[str], rows: list[list]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def print_file(path: str) -> None:
    """Print a file's content to stdout with a header."""
    print(f"\n{'='*70}")
    print(f"  OUTPUT: {path}")
    print(f"{'='*70}")
    with open(path, encoding="utf-8") as f:
        print(f.read())


# ---------------------------------------------------------------------------
# 1. Ingredient frequency
# ---------------------------------------------------------------------------

def report_ingredient_frequency(recipes: list[dict], out: str) -> None:
    print("[1/5] Computing ingredient frequency...")

    # ingredient_name → list of recipe names
    ing_recipes: dict[str, list[str]] = defaultdict(list)

    for recipe in recipes:
        recipe_name = recipe.get("name", "UNKNOWN")
        for ing in recipe.get("ingredients", []):
            name = ing.get("name", "").strip()
            if name:
                ing_recipes[name].append(recipe_name)

    rows = []
    for ing_name, r_names in sorted(ing_recipes.items(), key=lambda x: -len(x[1])):
        rows.append([ing_name, len(r_names), "; ".join(r_names)])

    write_csv(out, ["ingredient_name", "recipe_count", "recipe_names"], rows)
    print(f"       → {len(rows)} unique ingredients written to {out}")
    print_file(out)


# ---------------------------------------------------------------------------
# 2. Unit inventory
# ---------------------------------------------------------------------------

def report_unit_inventory(recipes: list[dict], out: str) -> None:
    print("[2/5] Computing unit inventory...")

    # unit → (count, example ingredient)
    unit_counter: Counter = Counter()
    unit_example: dict[str | None, str] = {}

    for recipe in recipes:
        for ing in recipe.get("ingredients", []):
            unit = ing.get("unit")
            # Normalize None and empty string for display
            unit_key = unit if unit else None
            unit_counter[unit_key] += 1
            if unit_key not in unit_example:
                unit_example[unit_key] = ing.get("name", "")

    rows = []
    for unit, count in unit_counter.most_common():
        display_unit = str(unit) if unit is not None else "<null>"
        rows.append([display_unit, count, unit_example[unit]])

    write_csv(out, ["unit", "count", "example"], rows)
    print(f"       → {len(rows)} unique units written to {out}")
    print_file(out)


# ---------------------------------------------------------------------------
# 3. Amount anomalies
# ---------------------------------------------------------------------------

def report_amount_anomalies(recipes: list[dict], out: str) -> None:
    print("[3/5] Scanning for amount anomalies...")

    lines: list[str] = []
    lines.append("AMOUNT ANOMALIES REPORT")
    lines.append("=" * 50)
    lines.append("")
    lines.append("Cases where amount is null, zero, negative, or non-numeric.")
    lines.append("")

    count = 0
    for recipe in recipes:
        recipe_name = recipe.get("name", "UNKNOWN")
        for ing in recipe.get("ingredients", []):
            amount = ing.get("amount")
            unit = ing.get("unit")
            ing_name = ing.get("name", "")
            anomaly = None

            if amount is None:
                anomaly = "null"
            elif isinstance(amount, str):
                anomaly = f"non-numeric string: \"{amount}\""
            elif isinstance(amount, (int, float)):
                if amount == 0:
                    anomaly = "zero"
                elif amount < 0:
                    anomaly = f"negative: {amount}"

            if anomaly:
                count += 1
                lines.append(
                    f"  [{count}] Recipe: {recipe_name}"
                )
                lines.append(
                    f"       Ingredient: {ing_name}"
                )
                lines.append(
                    f"       amount={json.dumps(amount)}, unit={json.dumps(unit)}"
                )
                lines.append(
                    f"       Anomaly: {anomaly}"
                )
                lines.append("")

    lines.insert(4, f"Total anomalies found: {count}")

    text = "\n".join(lines)
    Path(out).write_text(text, encoding="utf-8")
    print(f"       → {count} anomalies written to {out}")
    print_file(out)


# ---------------------------------------------------------------------------
# 4. Ingredient clusters (textual similarity)
# ---------------------------------------------------------------------------

def report_ingredient_clusters(recipes: list[dict], out: str) -> None:
    print("[4/5] Computing ingredient similarity clusters...")

    # Gather all unique ingredient names with their recipes
    ing_recipes: dict[str, list[str]] = defaultdict(list)
    for recipe in recipes:
        recipe_name = recipe.get("name", "UNKNOWN")
        for ing in recipe.get("ingredients", []):
            name = ing.get("name", "").strip()
            if name:
                ing_recipes[name].append(recipe_name)

    names = sorted(ing_recipes.keys())

    # Build clusters via SequenceMatcher
    THRESHOLD = 0.75
    visited: set[str] = set()
    clusters: list[list[str]] = []

    for i, a in enumerate(names):
        if a in visited:
            continue
        cluster = [a]
        a_lower = a.lower()
        for j in range(i + 1, len(names)):
            b = names[j]
            if b in visited:
                continue
            b_lower = b.lower()
            # SequenceMatcher ratio
            ratio = difflib.SequenceMatcher(None, a_lower, b_lower).ratio()
            if ratio >= THRESHOLD:
                cluster.append(b)
                visited.add(b)
            else:
                # Token overlap fallback: if tokens are subsets
                tokens_a = set(a_lower.split())
                tokens_b = set(b_lower.split())
                if len(tokens_a) >= 2 and len(tokens_b) >= 2:
                    overlap = len(tokens_a & tokens_b)
                    min_len = min(len(tokens_a), len(tokens_b))
                    if min_len > 0 and overlap / min_len >= 0.75:
                        cluster.append(b)
                        visited.add(b)

        if len(cluster) > 1:
            clusters.append(cluster)
            visited.add(a)

    # Write
    lines: list[str] = []
    lines.append("INGREDIENT SIMILARITY CLUSTERS")
    lines.append("=" * 50)
    lines.append("")
    lines.append(f"Threshold: SequenceMatcher ratio >= {THRESHOLD} OR token overlap >= 75%")
    lines.append(f"Clusters found: {len(clusters)}")
    lines.append("")
    lines.append("These are CANDIDATES for manual review — not a decision.")
    lines.append("")

    for idx, cluster in enumerate(clusters, 1):
        lines.append(f"--- Cluster {idx} ({len(cluster)} variants) ---")
        for name in cluster:
            r_list = "; ".join(ing_recipes[name])
            lines.append(f"  \"{name}\" ({len(ing_recipes[name])} recipes: {r_list})")
        lines.append("")

    text = "\n".join(lines)
    Path(out).write_text(text, encoding="utf-8")
    print(f"       → {len(clusters)} clusters written to {out}")
    print_file(out)


# ---------------------------------------------------------------------------
# 5. Summary report (Markdown)
# ---------------------------------------------------------------------------

GLASS_PATTERNS: dict[str, re.Pattern] = {
    "old fashioned": re.compile(r"old.?fashioned", re.I),
    "cocktail glass": re.compile(r"cocktail\s+glass", re.I),
    "highball": re.compile(r"highball", re.I),
    "coupe": re.compile(r"coupe", re.I),
    "martini glass": re.compile(r"martini\s+glass", re.I),
    "collins": re.compile(r"collins", re.I),
    "champagne flute": re.compile(r"champagne\s+flute", re.I),
    "hurricane": re.compile(r"hurricane", re.I),
    "rocks": re.compile(r"rocks\s+glass", re.I),
    "wine glass": re.compile(r"wine\s+glass", re.I),
    "shot": re.compile(r"shot\s+glass", re.I),
    "copper mug": re.compile(r"copper\s+mug", re.I),
    "snifter": re.compile(r"snifter", re.I),
    "tumbler": re.compile(r"tumbler", re.I),
    "flute": re.compile(r"\bflute\b", re.I),
}

METHOD_PATTERNS: dict[str, re.Pattern] = {
    "shake": re.compile(r"\bshake\b", re.I),
    "stir": re.compile(r"\bstir\b", re.I),
    "build": re.compile(r"\bbuild\b", re.I),
    "blend": re.compile(r"\bblend\b", re.I),
    "muddle": re.compile(r"\bmuddle\b", re.I),
    "layer": re.compile(r"\blayer\b", re.I),
}


def report_summary(recipes: list[dict], out: str) -> None:
    print("[5/5] Generating summary report...")

    total = len(recipes)

    # Category breakdown
    cat_counter: Counter = Counter()
    for r in recipes:
        cat_counter[r.get("iba_category", "unknown")] += 1

    # Ingredient stats
    ing_per_recipe: list[int] = []
    all_ing_names: set[str] = set()
    ing_freq: Counter = Counter()

    for r in recipes:
        ings = r.get("ingredients", [])
        ing_per_recipe.append(len(ings))
        for ing in ings:
            name = ing.get("name", "").strip()
            if name:
                all_ing_names.add(name)
                ing_freq[name] += 1

    unique_count = len(all_ing_names)
    mean_ing = statistics.mean(ing_per_recipe) if ing_per_recipe else 0
    median_ing = statistics.median(ing_per_recipe) if ing_per_recipe else 0
    min_ing = min(ing_per_recipe) if ing_per_recipe else 0
    max_ing = max(ing_per_recipe) if ing_per_recipe else 0
    sorted_counts = sorted(ing_per_recipe)
    p95_idx = int(len(sorted_counts) * 0.95)
    p95_ing = sorted_counts[min(p95_idx, len(sorted_counts) - 1)] if sorted_counts else 0

    # Top 20 ingredients
    top20 = ing_freq.most_common(20)

    # Rare ingredients (count == 1)
    rare = [name for name, count in ing_freq.items() if count == 1]
    rare.sort()

    # Glass extraction from method
    glass_counter: Counter = Counter()
    for r in recipes:
        method = r.get("method", "") or ""
        for glass_name, pattern in GLASS_PATTERNS.items():
            if pattern.search(method):
                glass_counter[glass_name] += 1

    # Method type extraction
    method_counter: Counter = Counter()
    for r in recipes:
        method = r.get("method", "") or ""
        for method_type, pattern in METHOD_PATTERNS.items():
            if pattern.search(method):
                method_counter[method_type] += 1

    # Build markdown
    lines: list[str] = []
    lines.append("# IBA Cocktails — Descriptive Summary")
    lines.append("")
    lines.append("## Overview")
    lines.append("")
    lines.append(f"- **Total recipes**: {total}")
    lines.append("")
    lines.append("### Category breakdown")
    lines.append("")
    lines.append("| Category | Count |")
    lines.append("|----------|-------|")
    for cat, count in cat_counter.most_common():
        lines.append(f"| {cat} | {count} |")
    lines.append("")

    lines.append("## Ingredients")
    lines.append("")
    lines.append(f"- **Unique ingredient names**: {unique_count}")
    lines.append(f"- **Ingredients per recipe**: mean={mean_ing:.1f}, "
                 f"median={median_ing}, min={min_ing}, max={max_ing}, p95={p95_ing}")
    lines.append("")

    lines.append("### Top 20 most frequent ingredients")
    lines.append("")
    lines.append("| # | Ingredient | Recipes |")
    lines.append("|---|-----------|---------|")
    for rank, (name, count) in enumerate(top20, 1):
        lines.append(f"| {rank} | {name} | {count} |")
    lines.append("")

    lines.append(f"### Rare ingredients (single use) — {len(rare)} total")
    lines.append("")
    for name in rare:
        lines.append(f"- {name}")
    lines.append("")

    lines.append("## Glassware (extracted from method text)")
    lines.append("")
    lines.append("| Glass | Mentions |")
    lines.append("|-------|----------|")
    for glass, count in glass_counter.most_common():
        lines.append(f"| {glass} | {count} |")
    if not glass_counter:
        lines.append("| (none found) | 0 |")
    lines.append("")

    lines.append("## Method types (extracted from method text)")
    lines.append("")
    lines.append("| Technique | Recipes |")
    lines.append("|-----------|---------|")
    for method_type, count in method_counter.most_common():
        lines.append(f"| {method_type} | {count} |")
    if not method_counter:
        lines.append("| (none found) | 0 |")
    lines.append("")

    text = "\n".join(lines)
    Path(out).write_text(text, encoding="utf-8")
    print(f"       → Summary written to {out}")
    print_file(out)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python analyze_iba.py <path_to_iba_cocktails.json>")
        sys.exit(1)

    input_path = sys.argv[1]
    if not Path(input_path).exists():
        print(f"Error: file not found: {input_path}")
        sys.exit(1)

    print(f"Loading {input_path}...")
    recipes = load_data(input_path)
    print(f"Loaded {len(recipes)} recipes.\n")

    report_ingredient_frequency(recipes, "report_ingredient_frequency.csv")
    report_unit_inventory(recipes, "report_unit_inventory.csv")
    report_amount_anomalies(recipes, "report_amount_anomalies.txt")
    report_ingredient_clusters(recipes, "report_ingredient_clusters.txt")
    report_summary(recipes, "report_summary.md")

    print("\n" + "=" * 70)
    print("  ALL REPORTS GENERATED SUCCESSFULLY")
    print("=" * 70)


if __name__ == "__main__":
    main()
