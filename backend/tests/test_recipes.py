def test_recipes_list_default_pagination(client):
    resp = client.get("/api/recipes")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 12
    assert len(data["items"]) == 12
    # Sorted by name — first two alphabetically
    assert data["items"][0]["name"] == "Test Americano"
    assert data["items"][1]["name"] == "Test Aperol Spritz"
    # ingredient_count present
    for item in data["items"]:
        assert "ingredient_count" in item
    # Negroni has 4 ingredients (2 mandatory + 1 optional + 1 garnish)
    negroni = next(i for i in data["items"] if i["name"] == "Test Negroni")
    assert negroni["ingredient_count"] == 4
    # Mule has 2 ingredients (alternatives)
    mule = next(i for i in data["items"] if i["name"] == "Test Mule")
    assert mule["ingredient_count"] == 2


def test_recipes_list_category_filter(client):
    resp = client.get("/api/recipes?category=unforgettable")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    names = sorted(i["name"] for i in data["items"])
    assert "Test Negroni" in names


def test_recipes_list_search(client):
    resp = client.get("/api/recipes?search=mule")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    names = sorted(i["name"] for i in data["items"])
    assert names == ["Test Generic Mule", "Test Mule"]


def test_recipes_detail_returns_full_recipe(client):
    # Fetch list to get real ID
    list_resp = client.get("/api/recipes?search=negroni")
    recipe_id = list_resp.json()["items"][0]["id"]

    resp = client.get(f"/api/recipes/{recipe_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Test Negroni"
    assert data["iba_category"] == "unforgettable"
    assert data["method"] == "Stir and strain"
    assert data["glass"] == "old fashioned"
    assert data["garnish"] == "Orange peel"
    assert data["source_url"] == "https://example.com/negroni"
    assert len(data["ingredients"]) == 4

    mandatory = [i for i in data["ingredients"]
                 if not i["is_optional"] and not i["is_garnish"]]
    assert len(mandatory) == 2
    for ing in mandatory:
        assert ing["amount"] == 30.0
        assert ing["unit"] == "ml"
        assert ing["alternative_group_id"] is None


def test_recipes_detail_404_for_missing_id(client):
    resp = client.get("/api/recipes/99999")
    assert resp.status_code == 404


def test_recipes_with_alternative_group_returns_grouped_ingredients(client):
    list_resp = client.get("/api/recipes?search=mule")
    # Pick "Test Mule" specifically — it has alt groups; "Test Generic Mule" does not
    mule = [r for r in list_resp.json()["items"] if r["name"] == "Test Mule"][0]
    recipe_id = mule["id"]

    resp = client.get(f"/api/recipes/{recipe_id}")
    assert resp.status_code == 200
    data = resp.json()

    ingredients = data["ingredients"]
    assert len(ingredients) == 2

    alt_ids = [i["alternative_group_id"] for i in ingredients]
    # Both ingredients share the same non-null alternative_group_id
    assert all(a is not None for a in alt_ids)
    assert alt_ids[0] == alt_ids[1]
