import uuid

BAD_UUID = "00000000-0000-0000-0000-000000000000"


def test_health_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_quote_returns_201_and_persists(client, child):
    response = client.post(
        "/quotes",
        json={"child_id": str(child.id), "text": "My sock is angry"},
    )
    assert response.status_code == 201

    body = response.json()
    assert body["text"] == "My sock is angry"
    assert body["child_id"] == str(child.id)
    # Server-assigned fields come back populated.
    assert uuid.UUID(body["id"])
    assert body["said_on"]


def test_create_quote_strips_surrounding_whitespace(client, child):
    response = client.post(
        "/quotes",
        json={"child_id": str(child.id), "text": "  spaced out  "},
    )
    assert response.status_code == 201
    assert response.json()["text"] == "spaced out"


def test_create_quote_with_blank_text_returns_422(client, child):
    response = client.post(
        "/quotes",
        json={"child_id": str(child.id), "text": "   "},
    )
    assert response.status_code == 422


def test_create_quote_with_nonexistent_child_returns_404(client):
    response = client.post(
        "/quotes",
        json={"child_id": BAD_UUID, "text": "orphan quote"},
    )
    assert response.status_code == 404


def test_create_quote_with_malformed_uuid_returns_422(client):
    response = client.post(
        "/quotes",
        json={"child_id": "not-a-uuid", "text": "bad id"},
    )
    assert response.status_code == 422


def test_get_quote_returns_the_created_quote(client, child):
    created = client.post(
        "/quotes", json={"child_id": str(child.id), "text": "Find me"}
    ).json()

    response = client.get(f"/quotes/{created['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_nonexistent_quote_returns_404(client):
    response = client.get(f"/quotes/{BAD_UUID}")
    assert response.status_code == 404


def test_delete_quote_hides_it_from_reads(client, child):
    created = client.post(
        "/quotes", json={"child_id": str(child.id), "text": "Delete me"}
    ).json()

    assert client.delete(f"/quotes/{created['id']}").status_code == 204
    assert client.get(f"/quotes/{created['id']}").status_code == 404
    assert client.delete(f"/quotes/{created['id']}").status_code == 404


def test_deleted_quote_is_excluded_from_list(client, child):
    created = client.post(
        "/quotes", json={"child_id": str(child.id), "text": "Temporary"}
    ).json()
    client.delete(f"/quotes/{created['id']}")

    body = client.get(f"/quotes?child_id={child.id}").json()
    assert body["total"] == 0
    assert body["items"] == []


def test_list_filters_by_child(client, child, db):
    from app.models import Child

    other = Child(user_id=child.user_id, name="Bo")
    db.add(other)
    db.flush()

    client.post("/quotes", json={"child_id": str(child.id), "text": "Ada said this"})
    client.post("/quotes", json={"child_id": str(other.id), "text": "Bo said this"})

    body = client.get(f"/quotes?child_id={child.id}").json()
    assert body["total"] == 1
    assert body["items"][0]["text"] == "Ada said this"


def test_list_pagination_slices_results(client, child):
    for i in range(5):
        client.post("/quotes", json={"child_id": str(child.id), "text": f"Quote {i}"})

    first = client.get(f"/quotes?child_id={child.id}&limit=2&offset=0").json()
    second = client.get(f"/quotes?child_id={child.id}&limit=2&offset=2").json()

    assert first["total"] == 5
    assert len(first["items"]) == 2
    assert len(second["items"]) == 2
    # Pages must not overlap.
    first_ids = {item["id"] for item in first["items"]}
    second_ids = {item["id"] for item in second["items"]}
    assert first_ids.isdisjoint(second_ids)


def test_list_offset_beyond_end_returns_empty_page(client, child):
    client.post("/quotes", json={"child_id": str(child.id), "text": "Only one"})

    body = client.get(f"/quotes?child_id={child.id}&limit=10&offset=99").json()
    assert body["total"] == 1
    assert body["items"] == []


def test_list_rejects_invalid_pagination_values(client):
    assert client.get("/quotes?limit=0").status_code == 422
    assert client.get("/quotes?limit=101").status_code == 422
    assert client.get("/quotes?offset=-1").status_code == 422
