"""Tests for GET /api/bottles/optimize-next."""

_FLAVOR = {
    "sweet": 0, "bitter": 0, "sour": 0, "citrusy": 0,
    "fruity": 0, "herbal": 0, "floral": 0, "spicy": 0,
    "smoky": 0, "vanilla": 0, "woody": 0, "minty": 0,
    "earthy": 0, "umami": 0, "body": 0, "intensity": 0,
}


def _add_bottle(client, class_name, brand, label="v1"):
    return client.post("/api/bottles", json={
        "class_name": class_name, "brand": brand, "label": label,
        "abv": 40.0, "on_hand": True, "flavor_profile": _FLAVOR,
    })


def _cleanup_bottles(client):
    for b in client.get("/api/bottles").json()["items"]:
        client.delete(f"/api/bottles/{b['id']}")


def test_optimize_next_returns_ranked_list(client):
    """With empty inventory, optimize-next returns candidates sorted by delta desc."""
    _cleanup_bottles(client)
    resp = client.get("/api/bottles/optimize-next")
    assert resp.status_code == 200
    data = resp.json()

    assert data["current_state"]["currently_feasible"] >= 1  # Juice Mix always feasible
    candidates = data["ranked_candidates"]
    assert len(candidates) > 0

    # Verify descending delta order
    deltas = [c["delta"] for c in candidates]
    assert deltas == sorted(deltas, reverse=True)

    _cleanup_bottles(client)


def test_optimize_next_excludes_already_owned_classes(client):
    """Classes with on-hand bottles must not appear as candidates."""
    _cleanup_bottles(client)
    _add_bottle(client, "TestGin", "OwnedGin")

    resp = client.get("/api/bottles/optimize-next?include_zero=true")
    data = resp.json()
    candidate_names = {c["class_name"] for c in data["ranked_candidates"]}
    assert "TestGin" not in candidate_names

    _cleanup_bottles(client)


def test_optimize_next_excludes_commodities(client):
    """Commodity classes (TestSodaWater, TestOrangeJuice) must never appear."""
    _cleanup_bottles(client)
    resp = client.get("/api/bottles/optimize-next?include_zero=true&top=50")
    data = resp.json()
    candidate_names = {c["class_name"] for c in data["ranked_candidates"]}
    assert "TestSodaWater" not in candidate_names
    assert "TestOrangeJuice" not in candidate_names

    _cleanup_bottles(client)


def test_optimize_next_excludes_garnishes(client):
    """Garnish classes must never appear."""
    _cleanup_bottles(client)
    resp = client.get("/api/bottles/optimize-next?include_zero=true&top=50")
    data = resp.json()
    candidate_names = {c["class_name"] for c in data["ranked_candidates"]}
    assert "TestLemonWheel" not in candidate_names

    _cleanup_bottles(client)


def test_optimize_next_excludes_parent_families(client):
    """Root parent classes (TestSpirit, TestAperitif, etc.) must not appear."""
    _cleanup_bottles(client)
    resp = client.get("/api/bottles/optimize-next?include_zero=true&top=50")
    data = resp.json()
    candidate_names = {c["class_name"] for c in data["ranked_candidates"]}
    assert "TestSpirit" not in candidate_names
    assert "TestAperitif" not in candidate_names
    assert "TestGarnish" not in candidate_names
    assert "TestMixer" not in candidate_names

    _cleanup_bottles(client)


def test_optimize_next_includes_zero_when_flag_set(client):
    """With include_zero=true, candidates with delta=0 appear."""
    _cleanup_bottles(client)
    # Give enough bottles to make most recipes feasible
    _add_bottle(client, "TestGin", "ZeroGin")
    _add_bottle(client, "TestVodka", "ZeroVodka")
    _add_bottle(client, "TestCampari", "ZeroCampari")
    _add_bottle(client, "TestAperol", "ZeroAperol")

    # Without flag — no zero-delta
    resp = client.get("/api/bottles/optimize-next")
    data = resp.json()
    assert all(c["delta"] > 0 for c in data["ranked_candidates"])

    # With flag — zero-delta may appear
    resp2 = client.get("/api/bottles/optimize-next?include_zero=true&top=50")
    data2 = resp2.json()
    # TestBitters is referenced by Negroni as optional → never unlocks anything
    bitters = [c for c in data2["ranked_candidates"] if c["class_name"] == "TestBitters"]
    if bitters:
        assert bitters[0]["delta"] == 0

    _cleanup_bottles(client)


def test_optimize_next_top_parameter_truncates(client):
    """With ?top=2, at most 2 candidates are returned."""
    _cleanup_bottles(client)
    resp = client.get("/api/bottles/optimize-next?top=2")
    data = resp.json()
    assert len(data["ranked_candidates"]) <= 2

    _cleanup_bottles(client)


def test_optimize_next_unlocked_recipes_consistency(client):
    """For each candidate, verify the unlocked recipes are actually feasible
    when that candidate is hypothetically added."""
    _cleanup_bottles(client)
    _add_bottle(client, "TestGin", "ConsistencyGin")

    resp = client.get("/api/bottles/optimize-next")
    data = resp.json()
    currently_feasible = set(data["current_state"]["currently_feasible_recipes"])

    for cand in data["ranked_candidates"]:
        assert cand["delta"] == len(cand["unlocked_recipes"])
        for recipe in cand["unlocked_recipes"]:
            assert recipe["name"] not in currently_feasible

    _cleanup_bottles(client)


def test_optimize_next_deterministic_order(client):
    """Candidates with the same delta are ordered alphabetically by class_name."""
    _cleanup_bottles(client)
    resp = client.get("/api/bottles/optimize-next?include_zero=true&top=50")
    data = resp.json()
    candidates = data["ranked_candidates"]

    # Group by delta, check alphabetical within each group
    from itertools import groupby
    for _delta, group in groupby(candidates, key=lambda c: c["delta"]):
        names = [c["class_name"] for c in group]
        assert names == sorted(names)

    _cleanup_bottles(client)


def test_optimize_next_with_empty_inventory(client):
    """With zero bottles, top picks should include the most-connected classes."""
    _cleanup_bottles(client)
    resp = client.get("/api/bottles/optimize-next?top=50")
    data = resp.json()

    # Currently feasible should be only all-commodity recipes (Juice Mix)
    assert data["current_state"]["currently_feasible"] >= 1

    # With grouping, representatives and their alternatives all count
    all_names = set()
    for c in data["ranked_candidates"]:
        all_names.add(c["class_name"])
        for a in c.get("equivalent_alternatives", []):
            all_names.add(a["class_name"])
    # TestGin/TestVodka appear as representative or alternative
    assert "TestGin" in all_names or "TestVodka" in all_names

    _cleanup_bottles(client)


def test_optimize_next_with_full_inventory_returns_empty(client):
    """If user has all non-commodity leaf classes, ranking is empty or all delta=0."""
    _cleanup_bottles(client)
    _add_bottle(client, "TestGin", "FullGin")
    _add_bottle(client, "TestVodka", "FullVodka")
    _add_bottle(client, "TestBitters", "FullBitters")
    _add_bottle(client, "TestCampari", "FullCampari")
    _add_bottle(client, "TestAperol", "FullAperol")

    resp = client.get("/api/bottles/optimize-next")
    data = resp.json()
    # All recipes feasible (generics satisfied via wildcard), no delta > 0
    assert len(data["ranked_candidates"]) == 0

    _cleanup_bottles(client)


def test_optimize_next_alternative_group_handling(client):
    """Test Boulevardier requires (TestGin OR TestVodka) + TestCampari.
    With TestGin owned: adding TestVodka should NOT unlock Boulevardier
    (alt group already satisfied). Adding TestCampari SHOULD unlock it."""
    _cleanup_bottles(client)
    _add_bottle(client, "TestGin", "AltGin")

    resp = client.get("/api/bottles/optimize-next?top=50")
    data = resp.json()
    candidates = {c["class_name"]: c for c in data["ranked_candidates"]}

    # TestVodka may appear as representative or grouped under TestVodka (generic)
    # Either way, it should NOT unlock Boulevardier (alt group satisfied by TestGin)
    vodka_rep = candidates.get("TestVodka") or candidates.get("TestVodka (generic)")
    if vodka_rep:
        vodka_unlocked = {r["name"] for r in vodka_rep["unlocked_recipes"]}
        assert "Test Boulevardier" not in vodka_unlocked

    # TestCampari SHOULD unlock Boulevardier (it's the missing mandatory ingredient)
    assert "TestCampari" in candidates
    campari_unlocked = {r["name"] for r in candidates["TestCampari"]["unlocked_recipes"]}
    assert "Test Boulevardier" in campari_unlocked

    _cleanup_bottles(client)

    # Without either Gin or Vodka: adding one of them should unlock Mule + Spritz
    # but NOT Boulevardier (still needs Campari)
    resp2 = client.get("/api/bottles/optimize-next?top=50")
    data2 = resp2.json()
    candidates2 = {c["class_name"]: c for c in data2["ranked_candidates"]}

    # TestGin may be grouped under TestGin (generic) as representative
    gin_rep = candidates2.get("TestGin") or candidates2.get("TestGin (generic)")
    if gin_rep:
        gin_unlocked = {r["name"] for r in gin_rep["unlocked_recipes"]}
        assert "Test Boulevardier" not in gin_unlocked  # still needs Campari
        assert "Test Mule" in gin_unlocked


def test_optimize_next_does_not_suggest_generic_when_specific_owned(client):
    """Having TestGin satisfies all TestGin (generic) requirements via wildcard.
    The optimizer should NOT suggest TestGin (generic) as a useful purchase."""
    _cleanup_bottles(client)
    _add_bottle(client, "TestGin", "SpecificGin")

    resp = client.get("/api/bottles/optimize-next?include_zero=false")
    data = resp.json()
    candidate_names = {c["class_name"] for c in data["ranked_candidates"]}
    assert "TestGin (generic)" not in candidate_names

    _cleanup_bottles(client)


# -- equivalent grouping tests ------------------------------------------------


def test_optimize_next_groups_equivalent_candidates(client):
    """TestGin (generic) and TestLondonDryGin are siblings under TestGinFamily.
    Neither is directly referenced in recipes — they only satisfy
    TestGin (generic) requirements via wildcard/exact match, unlocking
    only Test Gin Fizz.  They must appear as 1 group with (generic) as
    representative and TestLondonDryGin as equivalent alternative."""
    _cleanup_bottles(client)

    resp = client.get("/api/bottles/optimize-next?top=50")
    data = resp.json()
    # TestGin has a higher delta (it's referenced directly in many recipes),
    # so it's a separate candidate.  The group is TestGin (generic) + TestLondonDryGin.
    gin_family = [
        c for c in data["ranked_candidates"]
        if c["parent_family"] == "TestGinFamily"
    ]
    # Two entries: TestGin (solo, higher delta) and the grouped entry
    assert len(gin_family) == 2
    grouped = next(c for c in gin_family if c["class_name"] == "TestGin (generic)")
    assert len(grouped["equivalent_alternatives"]) == 1
    assert grouped["equivalent_alternatives"][0]["class_name"] == "TestLondonDryGin"

    _cleanup_bottles(client)


def test_optimize_next_representative_is_generic_when_present(client):
    """When the group includes a '(generic)' class, that is the representative
    regardless of alphabetical order ('TestGin (generic)' > 'TestLondonDryGin'
    alphabetically, but generic wins)."""
    _cleanup_bottles(client)

    resp = client.get("/api/bottles/optimize-next?top=50")
    data = resp.json()
    grouped = next(
        (c for c in data["ranked_candidates"]
         if c["class_name"] == "TestGin (generic)"),
        None,
    )
    assert grouped is not None
    # "TestLondonDryGin" comes after "TestGin (generic)" alphabetically,
    # but the key point is (generic) is representative, not alphabetical first
    alt_names = {a["class_name"] for a in grouped["equivalent_alternatives"]}
    assert "TestLondonDryGin" in alt_names

    _cleanup_bottles(client)


def test_optimize_next_does_not_group_when_unlocks_differ(client):
    """TestGin and TestCampari are from different families and unlock different
    recipes.  They must remain separate candidates."""
    _cleanup_bottles(client)

    resp = client.get("/api/bottles/optimize-next?top=50")
    data = resp.json()
    candidates = {c["class_name"]: c for c in data["ranked_candidates"]}

    gin_rep = candidates.get("TestGin (generic)") or candidates.get("TestGin")
    campari = candidates.get("TestCampari")
    assert gin_rep is not None
    assert campari is not None
    assert gin_rep["class_id"] != campari["class_id"]

    # Neither is an alternative of the other
    gin_alt_ids = {a["class_id"] for a in gin_rep["equivalent_alternatives"]}
    assert campari["class_id"] not in gin_alt_ids

    _cleanup_bottles(client)


def test_optimize_next_top_counts_groups_not_raw(client):
    """With top=1, exactly 1 grouped candidate is returned even though
    the underlying raw candidates are more numerous."""
    _cleanup_bottles(client)

    resp = client.get("/api/bottles/optimize-next?top=1")
    data = resp.json()
    assert len(data["ranked_candidates"]) == 1
    # The single entry may carry equivalent_alternatives
    cand = data["ranked_candidates"][0]
    assert "equivalent_alternatives" in cand

    _cleanup_bottles(client)


def test_optimize_next_no_alternatives_when_solo(client):
    """A candidate with no equivalent siblings has an empty
    equivalent_alternatives list."""
    _cleanup_bottles(client)

    resp = client.get("/api/bottles/optimize-next?top=50")
    data = resp.json()
    campari = next(
        (c for c in data["ranked_candidates"] if c["class_name"] == "TestCampari"),
        None,
    )
    assert campari is not None
    assert campari["equivalent_alternatives"] == []

    _cleanup_bottles(client)


def test_optimize_next_equivalent_alternatives_field_always_present(client):
    """Every candidate in the response must have the equivalent_alternatives field."""
    _cleanup_bottles(client)

    resp = client.get("/api/bottles/optimize-next?include_zero=true&top=50")
    data = resp.json()
    for cand in data["ranked_candidates"]:
        assert "equivalent_alternatives" in cand
        assert isinstance(cand["equivalent_alternatives"], list)

    _cleanup_bottles(client)
