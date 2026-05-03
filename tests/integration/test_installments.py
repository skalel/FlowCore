from datetime import date

import pytest


@pytest.fixture
def installment_data(client):
    """Prepara a hierarquia completa: Ambiente -> Holder -> Card -> Category."""

    env_resp = client.post(
        "/api/v1/environments", json={"type": "FAMILY", "name": "Env Cartões"}
    )
    env_id = env_resp.json()["id"]
    headers = {"X-Environment-Id": env_id}

    holder_payload = {"name": "Sandro FlowSpace", "cpf": "12345678901"}
    holder_resp = client.post(
        "/api/v1/card-holders", json=holder_payload, headers=headers
    )
    assert holder_resp.status_code == 201 or holder_resp.status_code == 200
    holder_id = holder_resp.json()["id"]

    card_payload = {
        "last4": "1234",
        "due_day": 10,
        "pay_day": 15,
        "holder_id": holder_id,
    }
    card_resp = client.post("/api/v1/cards", json=card_payload, headers=headers)
    assert card_resp.status_code == 200
    card_id = card_resp.json()["id"]

    cat_resp = client.post(
        "/api/v1/categories",
        json={"name": "Eletrônicos", "kind": "EXPENSE"},
        headers=headers,
    )
    cat_id = cat_resp.json()["id"]

    return {"env_id": env_id, "headers": headers, "cat_id": cat_id, "card_id": card_id}


def test_credit_card_installments_generation(client, installment_data):
    """
    Testa a geração de parcelas garantindo que os vínculos de
    Card e Holder estão íntegros.
    """
    headers = installment_data["headers"]
    hoje = date.today()

    payload = {
        "title": "Geladeira Nova",
        "total_amount": 1200.00,
        "total_installments": 3,
        "current_installment": 1,
        "current_due_date": str(hoje),
        "purchase_date": str(hoje),
        "category_id": installment_data["cat_id"],
        "payment_method": "CREDIT",
        "card_id": installment_data["card_id"],
        "generate_retroactive": True,
    }

    create_resp = client.post("/api/v1/installments", json=payload, headers=headers)
    assert create_resp.status_code == 200
    assert create_resp.json()["transactions_generated"] == 3

    resp_m1 = client.get(
        f"/api/v1/transactions?year={hoje.year}&month={hoje.month}", headers=headers
    )

    txs = resp_m1.json().get("current_month", [])
    parcela_1 = next((t for t in txs if "(1/3)" in t["description"]), None)

    assert parcela_1 is not None, "Parcela 1/3 não encontrada no mês atual"
    assert float(parcela_1["amount"]) == 400.00
    assert parcela_1["card_id"] == installment_data["card_id"]
