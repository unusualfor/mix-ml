"""Tests for /api/cocktails/can-make-now and /api/cocktails/{id}/feasibility."""

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


def test_can_make_now_with_empty_inventory_returns_zero(client):
    _cleanup_bottles(client)
    resp = client.get("/api/cocktails/can-make-now?status=all")
    assert resp.status_code == 200
    data = resp.json()
    # With commodities: Test Juice Mix (all-commodity) is always feasible
    assert data["summary"]["can_make"] == 1
    assert data["summary"]["cannot_make"] == 3  # Negroni, Mule, Spritz
    assert data["summary"]["on_hand_classes"] == 0


def test_can_make_now_with_full_inventory_returns_all(client):
    """Both test recipes need TestGin+TestVodka (Negroni mandatory) or
    either one (Mule alt_group). Give both → both recipes feasible."""
    _cleanup_bottles(client)
    _add_bottle(client, "TestGin", "FullInv Gin")
    _add_bottle(client, "TestVodka", "FullInv Vodka")

    resp = client.get("/api/cocktails/can-make-now?status=can_make")
    assert resp.status_code == 200
    data = resp.json()
    # Negroni, Mule, Spritz (spirit satisfied), Juice Mix (all-commodity)
    assert data["summary"]["can_make"] == 4
    names = sorted(i["name"] for i in data["items"])
    assert names == ["Test Juice Mix", "Test Mule", "Test Negroni", "Test Spritz"]

    _cleanup_bottles(client)


def test_can_make_now_handles_alternative_group(client):
    """Test Mule has alt_group: TestGin OR TestVodka.
    With only TestGin → Mule is feasible.
    With only TestVodka → Mule is feasible.
    With neither → Mule not feasible."""
    _cleanup_bottles(client)

    # Only gin → Mule feasible (alt group satisfied), Negroni not (needs vodka too)
    _add_bottle(client, "TestGin", "AltTest Gin")
    resp = client.get("/api/cocktails/can-make-now?status=all")
    data = resp.json()
    items = {i["name"]: i for i in data["items"]}
    assert items["Test Mule"]["can_make"] is True
    assert items["Test Negroni"]["can_make"] is False

    _cleanup_bottles(client)

    # Only vodka → Mule feasible (alt satisfied by vodka)
    _add_bottle(client, "TestVodka", "AltTest Vodka")
    resp2 = client.get("/api/cocktails/can-make-now?status=all")
    items2 = {i["name"]: i for i in resp2.json()["items"]}
    assert items2["Test Mule"]["can_make"] is True

    _cleanup_bottles(client)


def test_can_make_now_ignores_optional_ingredients(client):
    """Test Negroni has TestBitters as optional. Should be feasible
    even without a bottle for TestBitters, as long as mandatory ones are met."""
    _cleanup_bottles(client)
    _add_bottle(client, "TestGin", "OptTest Gin")
    _add_bottle(client, "TestVodka", "OptTest Vodka")

    resp = client.get("/api/cocktails/can-make-now?status=all")
    items = {i["name"]: i for i in resp.json()["items"]}
    assert items["Test Negroni"]["can_make"] is True

    _cleanup_bottles(client)


def test_can_make_now_ignores_garnish(client):
    """Test Negroni has TestLemonWheel as garnish. Should be feasible
    without a bottle for the garnish class."""
    _cleanup_bottles(client)
    _add_bottle(client, "TestGin", "GarnTest Gin")
    _add_bottle(client, "TestVodka", "GarnTest Vodka")

    resp = client.get("/api/cocktails/can-make-now?status=all")
    items = {i["name"]: i for i in resp.json()["items"]}
    # Negroni requires TestGin + TestVodka (mandatory). Optional + garnish ignored.
    assert items["Test Negroni"]["can_make"] is True
    assert items["Test Negroni"]["missing_count"] == 0

    _cleanup_bottles(client)


def test_feasibility_returns_missing_classes_when_not_makeable(client):
    """Test Negroni with only TestGin → missing TestVodka."""
    _cleanup_bottles(client)
    _add_bottle(client, "TestGin", "FeasTest Gin")

    # Get negroni ID
    list_resp = client.get("/api/recipes?search=negroni")
    recipe_id = list_resp.json()["items"][0]["id"]

    resp = client.get(f"/api/cocktails/{recipe_id}/feasibility")
    assert resp.status_code == 200
    data = resp.json()
    assert data["can_make"] is False

    # Check missing classes
    mandatory_ings = [i for i in data["ingredients"]
                      if not i["is_optional"] and not i["is_garnish"]]
    unsatisfied = [i for i in mandatory_ings if len(i["satisfied_by_bottles"]) == 0]
    assert len(unsatisfied) == 1
    assert unsatisfied[0]["class_name"] == "TestVodka"

    _cleanup_bottles(client)


# -- commodity ingredient tests ------------------------------------------------


def test_spritz_feasible_with_only_spirit_bottle(client):
    """Test Spritz needs TestGin (spirit) + TestSodaWater (commodity).
    With only a TestGin bottle, it should be feasible because the soda is commodity."""
    _cleanup_bottles(client)
    _add_bottle(client, "TestGin", "CommodityTest Gin")

    resp = client.get("/api/cocktails/can-make-now?status=all")
    items = {i["name"]: i for i in resp.json()["items"]}
    assert items["Test Spritz"]["can_make"] is True

    _cleanup_bottles(client)


def test_juice_mix_always_feasible_with_empty_inventory(client):
    """Test Juice Mix is all-commodity (TestSodaWater + TestOrangeJuice).
    Should always be feasible even with zero bottles."""
    _cleanup_bottles(client)

    resp = client.get("/api/cocktails/can-make-now?status=all")
    items = {i["name"]: i for i in resp.json()["items"]}
    assert items["Test Juice Mix"]["can_make"] is True
    assert items["Test Juice Mix"]["missing_count"] == 0

    _cleanup_bottles(client)


def test_missing_classes_excludes_commodities(client):
    """When Test Spritz is missing TestGin, the missing list should NOT
    include TestSodaWater (commodity). Only the spirit is listed."""
    _cleanup_bottles(client)

    resp = client.get("/api/cocktails/can-make-now?status=all")
    items = {i["name"]: i for i in resp.json()["items"]}
    assert items["Test Spritz"]["can_make"] is False
    assert items["Test Spritz"]["missing_count"] == 1
    assert "TestSodaWater" not in items["Test Spritz"]["missing_classes"]
    assert "TestGin" in items["Test Spritz"]["missing_classes"]

    _cleanup_bottles(client)


def test_feasibility_detail_marks_commodity_ingredients(client):
    """The /feasibility endpoint should mark commodity ingredients with is_commodity=True."""
    _cleanup_bottles(client)

    # Get Spritz recipe ID
    list_resp = client.get("/api/recipes?search=spritz")
    recipe_id = list_resp.json()["items"][0]["id"]

    resp = client.get(f"/api/cocktails/{recipe_id}/feasibility")
    assert resp.status_code == 200
    data = resp.json()

    ings = {i["class_name"]: i for i in data["ingredients"]}
    assert ings["TestGin"]["is_commodity"] is False
    assert ings["TestSodaWater"]["is_commodity"] is True

    _cleanup_bottles(client)


def test_classes_endpoint_includes_is_commodity_field(client):
    """The /classes endpoint should include is_commodity for all items."""
    resp = client.get("/api/classes?flat=true")
    data = resp.json()

    commodities = [c for c in data if c["is_commodity"]]
    non_commodities = [c for c in data if not c["is_commodity"]]
    commodity_names = sorted(c["name"] for c in commodities)
    assert commodity_names == ["TestOrangeJuice", "TestSodaWater"]
    assert len(non_commodities) == 7  # all others
