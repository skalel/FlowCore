import uuid

from app.api.auth_deps import get_current_user
from app.infra.db.orm_models import User
from main import app


def test_tenant_isolation_prevents_data_leak(client, db_session):
    """
    Garante que o Usuário B não consegue ler nem alterar o Ambiente do Usuário A,
    mesmo que ele descubra o UUID exato do ambiente.
    """

    env_resp = client.post(
        "/api/v1/environments",
        json={"type": "BUSINESS", "name": "Fortaleza do Usuário A"},
    )
    assert env_resp.status_code == 200
    env_id = env_resp.json()["id"]

    hacker = User(
        id=uuid.uuid4(),
        name="Sr. Hacker",
        email="hacker@malicioso.com",
        password_hash="fake_hash",
        plan_tier="free",
    )
    db_session.add(hacker)
    db_session.commit()

    app.dependency_overrides[get_current_user] = lambda: hacker

    try:
        malicious_get = client.get(
            "/api/v1/transactions?year=2026&month=4",
            headers={"X-Environment-Id": env_id},
        )

        assert malicious_get.status_code in [403, 404], (
            f"Falha de segurança! Status retornado: {malicious_get.status_code}"
        )

        malicious_delete = client.delete(f"/api/v1/environments/{env_id}")
        assert malicious_delete.status_code in [403, 404]

        malicious_patch = client.patch(
            f"/api/v1/environments/{env_id}",
            json={"settings": {"require_payment_confirmation": False}},
        )
        assert malicious_patch.status_code in [403, 404]

    finally:
        app.dependency_overrides.pop(get_current_user, None)
