import uuid


def test_create_environment_business(client):
    payload = {"type": "BUSINESS", "name": "FlowSpace Corp"}

    response = client.post("/api/v1/environments", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "BUSINESS"
    assert data["name"] == "FlowSpace Corp"


def test_create_environment_family(client):
    payload = {"type": "FAMILY", "name": "Minha Família"}

    response = client.post("/api/v1/environments", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "FAMILY"
    assert data["name"] == "Minha Família"
    assert data["is_owner"] is True
    assert data["settings"]["require_payment_confirmation"] is True
    assert data["settings"]["require_category_on_transactions"] is True


def test_list_environments(client):
    client.post("/api/v1/environments", json={"type": "FAMILY", "name": "Env 1"})
    client.post("/api/v1/environments", json={"type": "FRIENDS", "name": "Env 2"})

    response = client.get("/api/v1/environments")

    assert response.status_code == 200
    data = response.json()

    assert len(data) >= 2
    names = [env["name"] for env in data]
    assert "Env 1" in names
    assert "Env 2" in names


def test_update_environment_settings(client):
    create_resp = client.post(
        "/api/v1/environments", json={"type": "BUSINESS", "name": "Settings Test"}
    )
    env_id = create_resp.json()["id"]

    update_payload = {
        "settings": {
            "require_payment_confirmation": False,
            "require_category_on_transactions": False,
        }
    }
    patch_resp = client.patch(f"/api/v1/environments/{env_id}", json=update_payload)

    assert patch_resp.status_code == 200

    list_resp = client.get("/api/v1/environments")
    assert list_resp.status_code == 200
    environments = list_resp.json()

    updated_env = next((env for env in environments if env["id"] == env_id), None)

    assert updated_env is not None
    assert updated_env["settings"]["require_payment_confirmation"] is False
    assert updated_env["settings"]["require_category_on_transactions"] is False


def test_update_environment_not_found(client):
    fake_id = str(uuid.uuid4())

    update_payload = {"settings": {"require_payment_confirmation": False}}

    response = client.patch(f"/api/v1/environments/{fake_id}", json=update_payload)

    assert response.status_code == 404
