def test_classes_returns_hierarchical_tree(client):
    resp = client.get("/api/classes")
    assert resp.status_code == 200
    data = resp.json()

    # Five roots: TestAperitif, TestGarnish, TestMixer, TestSpirit, TestWine
    assert len(data) == 5
    roots = {r["name"]: r for r in data}

    spirit = roots["TestSpirit"]
    assert spirit["is_garnish"] is False
    assert spirit["is_commodity"] is False
    assert len(spirit["children"]) == 3

    child_names = sorted(c["name"] for c in spirit["children"])
    assert child_names == ["TestBitters", "TestGinFamily", "TestVodkaFamily"]

    garnish = roots["TestGarnish"]
    assert garnish["is_garnish"] is True
    assert len(garnish["children"]) == 1
    assert garnish["children"][0]["name"] == "TestLemonWheel"

    mixer = roots["TestMixer"]
    assert mixer["is_garnish"] is False
    assert mixer["is_commodity"] is False
    assert len(mixer["children"]) == 2
    for child in mixer["children"]:
        assert child["is_commodity"] is True

    aperitif = roots["TestAperitif"]
    assert len(aperitif["children"]) == 2


def test_classes_flat_returns_flat_list(client):
    resp = client.get("/api/classes?flat=true")
    assert resp.status_code == 200
    data = resp.json()

    assert len(data) == 20

    parents = [c for c in data if c["parent_id"] is None]
    children = [c for c in data if c["parent_id"] is not None]

    assert len(parents) == 5
    parent_names = sorted(p["name"] for p in parents)
    assert parent_names == ["TestAperitif", "TestGarnish", "TestMixer", "TestSpirit", "TestWine"]
    assert len(children) == 15
