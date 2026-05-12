#!/usr/bin/env python3
"""
Scraper for the IBA Official Cocktail List (2024 update).

Downloads all recipes from https://iba-world.com and saves them to
a structured JSON file (iba_cocktails.json).

Usage:
    python scrape_iba.py

Requirements:
    pip install requests beautifulsoup4
"""

import json
import logging
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup, Tag

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SITEMAP_URL = "https://iba-world.com/wp-sitemap-posts-iba-cocktail-1.xml"
OUTPUT_FILE = Path("iba_cocktails.json")
REQUEST_DELAY = 2  # seconds between requests
USER_AGENT = "Mozilla/5.0 (Cocktail-DB Builder)"
REQUEST_TIMEOUT = 30

# ---------------------------------------------------------------------------
# Category mapping (site text → normalised key)
# ---------------------------------------------------------------------------
CATEGORY_MAP = {
    "the unforgettables": "unforgettable",
    "unforgettables": "unforgettable",
    "unforgettable": "unforgettable",
    "contemporary classics": "contemporary",
    "contemporary": "contemporary",
    "new era": "new_era",
    "new era drinks": "new_era",
}

# ---------------------------------------------------------------------------
# Ingredient-parsing helpers
# ---------------------------------------------------------------------------
KNOWN_UNITS: set[str] = {
    "ml", "cl", "oz",
    "dash", "dashes",
    "drop", "drops",
    "tsp", "teaspoon", "teaspoons",
    "bsp", "barspoon", "barspoons",
    "pcs", "pc",
}

UNIT_NORMALIZE: dict[str, str] = {
    "dashes": "dash",
    "drop": "drops",
    "teaspoon": "tsp",
    "teaspoons": "tsp",
    "barspoon": "bsp",
    "barspoons": "bsp",
    "pc": "pcs",
}

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Networking
# ---------------------------------------------------------------------------

def get_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def fetch_page(session: requests.Session, url: str) -> BeautifulSoup | None:
    try:
        resp = session.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except requests.RequestException as exc:
        log.warning("  ✗ Failed to fetch %s: %s", url, exc)
        return None

# ---------------------------------------------------------------------------
# Index page
# ---------------------------------------------------------------------------

def normalize_category(raw: str) -> str | None:
    key = raw.strip().lower()
    for pattern, cat in CATEGORY_MAP.items():
        if pattern in key:
            return cat
    return None


def extract_cocktail_urls_from_sitemap(session: requests.Session) -> list[str]:
    """Fetch all cocktail URLs from the WordPress sitemap."""
    log.info("Fetching sitemap: %s", SITEMAP_URL)
    try:
        resp = session.get(SITEMAP_URL, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.error("Failed to fetch sitemap: %s", exc)
        return []
    urls = re.findall(r"<loc>([^<]+)</loc>", resp.text)
    return [u.strip() for u in urls]

# ---------------------------------------------------------------------------
# Ingredient parsing
# ---------------------------------------------------------------------------

def _parse_amount(raw: str) -> float | int | None:
    """Parse a numeric string, handling fractions like ``1/2``."""
    try:
        if "/" in raw:
            num, den = raw.split("/", 1)
            val = float(num) / float(den)
        else:
            val = float(raw)
        return int(val) if val == int(val) else round(val, 4)
    except (ValueError, ZeroDivisionError):
        return None


def parse_ingredient(line: str) -> dict | None:
    """Parse one ingredient line → ``{amount, unit, name}``."""
    line = line.strip()
    if not line:
        return None

    # 1) "{name} to top/fill"
    m = re.match(r"^(.+?)\s+to\s+(top|fill)\s*$", line, re.I)
    if m:
        return {"amount": None, "unit": "top", "name": m.group(1).strip()}

    # 2) "top/fill with {name}"
    m = re.match(r"^(?:top|fill)\s+(?:with\s+)?(.+)$", line, re.I)
    if m:
        return {"amount": None, "unit": "top", "name": m.group(1).strip()}

    # 3) "Few dashes/drops (of) {name}"
    m = re.match(r"^few\s+(dashes?|drops?)\s+(?:of\s+)?(.+)$", line, re.I)
    if m:
        unit = UNIT_NORMALIZE.get(m.group(1).lower(), m.group(1).lower())
        return {"amount": None, "unit": unit, "name": m.group(2).strip()}

    # 4) "{num} bar spoon(s) {name}"
    m = re.match(
        r"^([\d.]+(?:/[\d.]+)?)\s+bar\s+spoons?\s+(.+)$", line, re.I
    )
    if m:
        return {
            "amount": _parse_amount(m.group(1)),
            "unit": "bsp",
            "name": m.group(2).strip(),
        }

    # 5) "{num} {known_unit} (of) {name}"
    units_alt = "|".join(sorted(KNOWN_UNITS, key=len, reverse=True))
    m = re.match(
        rf"^([\d.]+(?:/[\d.]+)?)\s+({units_alt})\s+(?:of\s+)?(.+)$",
        line,
        re.I,
    )
    if m:
        unit = m.group(2).lower()
        unit = UNIT_NORMALIZE.get(unit, unit)
        return {
            "amount": _parse_amount(m.group(1)),
            "unit": unit,
            "name": m.group(3).strip(),
        }

    # 6) "{num} {name}" → counted item, unit = "whole"
    m = re.match(r"^([\d.]+(?:/[\d.]+)?)\s+(.+)$", line)
    if m:
        return {
            "amount": _parse_amount(m.group(1)),
            "unit": "whole",
            "name": m.group(2).strip(),
        }

    # 7) Bare ingredient name (no amount)
    return {"amount": None, "unit": None, "name": line}

# ---------------------------------------------------------------------------
# Recipe-page parsing
# ---------------------------------------------------------------------------

def _smart_title(text: str) -> str:
    """Title-case that preserves apostrophe contractions (Bee's Knees)."""
    return re.sub(
        r"[A-Za-z]+(['\u2019\u02BC][A-Za-z]+)?",
        lambda m: m.group(0)[0].upper() + m.group(0)[1:],
        text.lower(),
    )


def _collect_section_lines(heading: Tag) -> list[str]:
    """Collect text lines from the next Elementor widget sibling after *heading*'s widget."""
    # Navigate up to the elementor-element widget container (not elementor-widget-container)
    widget = heading.find_parent(
        "div", class_=lambda c: c and "elementor-element" in c and "elementor-widget-container" not in c
    )
    if widget is None:
        # Fallback: try direct next siblings of the heading
        lines: list[str] = []
        for sib in heading.find_next_siblings():
            if isinstance(sib, Tag) and sib.name and re.match(r"h[1-6]", sib.name):
                break
            text = sib.get_text(separator="\n", strip=True)
            for part in text.split("\n"):
                part = part.strip()
                if part:
                    lines.append(part)
        return lines

    # Get the next sibling elementor-element that contains the content
    content_div = widget.find_next_sibling(
        "div", class_=re.compile(r"elementor-element")
    )
    if content_div is None:
        return []

    text = content_div.get_text(separator="\n", strip=True)
    lines = []
    for part in text.split("\n"):
        part = part.strip()
        if part:
            lines.append(part)
    return lines


def parse_recipe_page(
    soup: BeautifulSoup, url: str
) -> dict | None:
    """Parse a single recipe page into structured data."""
    # Title from h1
    h1 = soup.find("h1")
    if not h1:
        log.warning("  ✗ No <h1> found on %s", url)
        return None
    name = _smart_title(h1.get_text(strip=True))

    # Category from breadcrumb link to /cocktail-category/…
    category: str | None = None
    for a_tag in soup.find_all("a", href=True):
        if "cocktail-category" in a_tag["href"]:
            category = normalize_category(a_tag.get_text(strip=True))
            if category:
                break

    # Locate h4 sections
    ingredients_lines: list[str] = []
    method_lines: list[str] = []
    garnish_lines: list[str] = []

    for h4 in soup.find_all("h4"):
        heading = h4.get_text(strip=True).upper()
        if "INGREDIENT" in heading:
            ingredients_lines = _collect_section_lines(h4)
        elif "METHOD" in heading:
            method_lines = _collect_section_lines(h4)
        elif "GARNISH" in heading:
            garnish_lines = _collect_section_lines(h4)

    ingredients = [
        ing
        for line in ingredients_lines
        if (ing := parse_ingredient(line)) is not None
    ]

    method = " ".join(method_lines).strip() or None
    garnish = " ".join(garnish_lines).strip() or None

    return {
        "name": name,
        "iba_category": category,
        "ingredients": ingredients,
        "method": method,
        "garnish": garnish,
        "source_url": url,
    }

# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def load_existing() -> list[dict]:
    if OUTPUT_FILE.exists():
        try:
            with open(OUTPUT_FILE, encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, IOError):
            return []
    return []


def save_cocktails(cocktails: list[dict]) -> None:
    cocktails.sort(key=lambda c: c["name"].lower())
    with open(OUTPUT_FILE, "w", encoding="utf-8") as fh:
        json.dump(cocktails, fh, indent=2, ensure_ascii=False)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    session = get_session()

    # Resume support
    existing = load_existing()
    existing_urls: set[str] = {c["source_url"] for c in existing}
    if existing:
        log.info(
            "Found %d existing recipes in %s — will skip them.",
            len(existing),
            OUTPUT_FILE,
        )

    # 1. Fetch cocktail URLs from sitemap
    cocktail_urls = extract_cocktail_urls_from_sitemap(session)
    if not cocktail_urls:
        log.error("No cocktail URLs found. Aborting.")
        sys.exit(1)
    total = len(cocktail_urls)
    log.info("Found %d cocktail URLs in sitemap.\n", total)
    time.sleep(REQUEST_DELAY)

    # 2. Scrape each recipe
    all_cocktails: list[dict] = list(existing)
    failed: list[str] = []

    for idx, url in enumerate(cocktail_urls, 1):
        # Ensure trailing slash for consistency
        url = url.rstrip("/") + "/"

        if url in existing_urls:
            log.info("[%d/%d] (skipped — already saved) %s", idx, total, url)
            continue

        log.info("[%d/%d] Fetching %s …", idx, total, url)
        soup = fetch_page(session, url)

        if soup is None:
            failed.append(url)
            time.sleep(REQUEST_DELAY)
            continue

        recipe = parse_recipe_page(soup, url)
        if recipe is None:
            log.warning("  ✗ Could not parse recipe from %s", url)
            failed.append(url)
        else:
            all_cocktails.append(recipe)
            log.info("  [%d/%d] %s → OK", idx, total, recipe["name"])
            # Incremental save for resume
            save_cocktails(all_cocktails)

        time.sleep(REQUEST_DELAY)

    # Final save
    save_cocktails(all_cocktails)

    # 4. Summary
    print("\n" + "=" * 55)
    print("  SCRAPING COMPLETE")
    print("=" * 55)
    print(f"  Total recipes saved : {len(all_cocktails)}")

    cats: dict[str, int] = {}
    for c in all_cocktails:
        k = c.get("iba_category") or "unknown"
        cats[k] = cats.get(k, 0) + 1
    print("\n  Breakdown by category:")
    for cat, count in sorted(cats.items()):
        print(f"    {cat:20s} {count}")

    if failed:
        print(f"\n  Failed ({len(failed)}):")
        for u in failed:
            print(f"    ✗ {u}")
    else:
        print("\n  No failures!")

    print(f"\n  Output → {OUTPUT_FILE.resolve()}")
    print("=" * 55)


if __name__ == "__main__":
    main()
