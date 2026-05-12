import json

_FLAVOR = {
    "sweet": 1, "bitter": 0, "sour": 1, "citrusy": 2,
    "fruity": 1, "herbal": 3, "floral": 2, "spicy": 1,
    "smoky": 0, "vanilla": 0, "woody": 0, "minty": 0,
    "earthy": 0, "umami": 0, "body": 2, "intensity": 4,
}


def _create_bottle(client, class_name="TestGin", brand="Acme Gin",
                   label="London Dry", abv=40.0, **overrides):
    body = {
        "class_name": class_name,
        "brand": brand,
        "label": label,
        "abv": abv,
        "on_hand": True,
        "flavor_profile": _FLAVOR,
        "notes": None,
        **overrides,
    }
    return client.post("/api/bottles", json=body)


def test_create_bottle_with_valid_class(client):
    resp = _create_bottle(client, brand="CreateTest Gin", label="CT1")
    assert resp.status_code == 201
    data = resp.json()
    assert data["class_name"] == "TestGin"
    assert data["family_name"] == "TestGinFamily"
    assert data["brand"] == "CreateTest Gin"
    assert data["abv"] == 40.0
    assert data["on_hand"] is True
    assert "id" in data
    assert "added_at" in data
    # Cleanup
    client.delete(f"/api/bottles/{data['id']}")


def test_create_bottle_unknown_class_returns_404(client):
    resp = _create_bottle(client, class_name="NonExistentSpirit",
                          brand="Ghost", label="Phantom")
    assert resp.status_code == 404
    assert "NonExistentSpirit" in resp.json()["detail"]


def test_create_bottle_invalid_flavor_profile_returns_422(client):
    # Missing key
    bad_flavor = {k: v for k, v in _FLAVOR.items() if k != "sweet"}
    resp = client.post("/api/bottles", json={
        "class_name": "TestGin", "brand": "Bad1", "label": "B1",
        "abv": 40.0, "flavor_profile": bad_flavor,
    })
    assert resp.status_code == 422

    # Value out of range
    bad_flavor2 = {**_FLAVOR, "sweet": 9}
    resp2 = client.post("/api/bottles", json={
        "class_name": "TestGin", "brand": "Bad2", "label": "B2",
        "abv": 40.0, "flavor_profile": bad_flavor2,
    })
    assert resp2.status_code == 422


def test_list_bottles_filters_by_on_hand(client):
    # Create two bottles: one on_hand, one not
    r1 = _create_bottle(client, brand="OnHand", label="OH1", on_hand=True)
    r2 = _create_bottle(client, brand="NotOnHand", label="NOH1", on_hand=False)
    id1, id2 = r1.json()["id"], r2.json()["id"]

    on = client.get("/api/bottles?on_hand=true").json()
    off = client.get("/api/bottles?on_hand=false").json()

    on_ids = {b["id"] for b in on["items"]}
    off_ids = {b["id"] for b in off["items"]}
    assert id1 in on_ids
    assert id2 in off_ids
    assert id2 not in on_ids

    client.delete(f"/api/bottles/{id1}")
    client.delete(f"/api/bottles/{id2}")


def test_list_bottles_filters_by_family(client):
    r1 = _create_bottle(client, brand="FamTest", label="FT1")
    id1 = r1.json()["id"]

    resp = client.get("/api/bottles?family=TestGinFamily")
    assert resp.status_code == 200
    ids = {b["id"] for b in resp.json()["items"]}
    assert id1 in ids

    resp2 = client.get("/api/bottles?family=NoSuchFamily")
    assert resp2.json()["total"] == 0

    client.delete(f"/api/bottles/{id1}")


def test_patch_bottle_on_hand_only(client):
    r = _create_bottle(client, brand="PatchTest", label="PT1", on_hand=True)
    bid = r.json()["id"]

    resp = client.patch(f"/api/bottles/{bid}", json={"on_hand": False})
    assert resp.status_code == 200
    assert resp.json()["on_hand"] is False

    # Verify persisted
    check = client.get(f"/api/bottles/{bid}").json()
    assert check["on_hand"] is False

    client.delete(f"/api/bottles/{bid}")


def test_patch_bottle_cannot_change_class(client):
    r = _create_bottle(client, brand="PatchClass", label="PC1")
    bid = r.json()["id"]

    # class_name and brand are not in BottlePatch — extra fields are ignored by Pydantic
    resp = client.patch(f"/api/bottles/{bid}",
                        json={"on_hand": False, "class_name": "TestVodka"})
    assert resp.status_code == 200
    # class_name should be unchanged
    assert resp.json()["class_name"] == "TestGin"

    client.delete(f"/api/bottles/{bid}")


def test_delete_bottle_returns_204(client):
    r = _create_bottle(client, brand="DeleteMe", label="DM1")
    bid = r.json()["id"]

    resp = client.delete(f"/api/bottles/{bid}")
    assert resp.status_code == 204

    resp2 = client.get(f"/api/bottles/{bid}")
    assert resp2.status_code == 404


def test_bulk_upsert_handles_duplicate_brand_label(client):
    bottles = [
        {"class_name": "TestGin", "brand": "BulkBrand", "label": "BL1",
         "abv": 40.0, "flavor_profile": _FLAVOR},
        {"class_name": "TestVodka", "brand": "BulkBrand", "label": "BL1",
         "abv": 37.5, "flavor_profile": _FLAVOR},
    ]
    resp = client.post("/api/bottles/_bulk", json=bottles)
    assert resp.status_code == 200
    data = resp.json()
    assert data["inserted"] == 2
    assert data["errors"] == []

    # Second call should upsert (update) — same brand+label
    resp2 = client.post("/api/bottles/_bulk", json=bottles)
    assert resp2.json()["inserted"] == 2

    # Verify we have exactly 1 row for BulkBrand/BL1 (not 2)
    listing = client.get("/api/bottles?class_name=TestVodka").json()
    bulk_bottles = [b for b in listing["items"]
                    if b["brand"] == "BulkBrand" and b["label"] == "BL1"]
    assert len(bulk_bottles) == 1
    assert bulk_bottles[0]["abv"] == 37.5  # last upsert wins

    # Cleanup
    for b in client.get("/api/bottles").json()["items"]:
        if b["brand"] == "BulkBrand":
            client.delete(f"/api/bottles/{b['id']}")
