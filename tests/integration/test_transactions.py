from datetime import date

import pytest


@pytest.fixture
def setup_data(client):
    """Cria um ambiente e categorias base para os testes de transação, evitando repetição de código."""

    env_resp = client.post(
        "/api/v1/environments", json={"type": "FAMILY", "name": "Env Transações"}
    )

    assert env_resp.status_code == 200, f"Falha ao criar ambiente: {env_resp.json()}"

    env_id = env_resp.json()["id"]

    headers = {"X-Environment-Id": env_id}

    cat_exp_resp = client.post(
        "/api/v1/categories",
        json={"name": "Alimentação", "kind": "EXPENSE"},
        headers=headers,
    )
    cat_exp_id = cat_exp_resp.json()["id"]

    cat_inc_resp = client.post(
        "/api/v1/categories",
        json={"name": "Salário", "kind": "INCOME"},
        headers=headers,
    )
    cat_inc_id = cat_inc_resp.json()["id"]

    return {
        "env_id": env_id,
        "headers": headers,
        "cat_exp_id": cat_exp_id,
        "cat_inc_id": cat_inc_id,
    }


def test_create_and_list_transaction(client, setup_data):
    payload = {
        "kind": "EXPENSE",
        "occurred_on": str(date.today()),
        "amount": 150.50,
        "description": "Almoço de Negócios",
        "category_id": setup_data["cat_exp_id"],
        "payment_method": "PIX",
    }

    create_resp = client.post(
        "/api/v1/transactions", json=payload, headers=setup_data["headers"]
    )
    assert create_resp.status_code == 200
    tx = create_resp.json()

    assert tx["amount"] == 150.50
    assert tx["paid_on"] is None

    list_resp = client.get(
        f"/api/v1/transactions?year={date.today().year}&month={date.today().month}",
        headers=setup_data["headers"],
    )
    assert list_resp.status_code == 200
    data = list_resp.json()

    assert len(data["current_month"]) >= 1
    assert data["current_month"][0]["description"] == "Almoço de Negócios"


def test_pay_expense_success(client, setup_data):
    payload = {
        "kind": "EXPENSE",
        "occurred_on": str(date.today()),
        "amount": 50.00,
        "description": "Uber",
        "category_id": setup_data["cat_exp_id"],
        "payment_method": "PIX",
    }
    tx_resp = client.post(
        "/api/v1/transactions", json=payload, headers=setup_data["headers"]
    )
    tx_id = tx_resp.json()["id"]

    today_str = str(date.today())
    patch_resp = client.patch(
        f"/api/v1/transactions/{tx_id}",
        json={"paid_on": today_str},
        headers=setup_data["headers"],
    )

    assert patch_resp.status_code == 200
    assert patch_resp.json()["paid_on"] == today_str


def test_pay_income_blocked(client, setup_data):
    """Garante que nossa regra de negócio que impede dar baixa em Receitas funcione."""

    payload = {
        "kind": "INCOME",
        "occurred_on": str(date.today()),
        "amount": 5000.00,
        "description": "Projeto Freelance",
        "category_id": setup_data["cat_inc_id"],
        "payment_method": "PIX",
    }
    tx_resp = client.post(
        "/api/v1/transactions", json=payload, headers=setup_data["headers"]
    )
    tx_id = tx_resp.json()["id"]

    patch_resp = client.patch(
        f"/api/v1/transactions/{tx_id}",
        json={"paid_on": str(date.today())},
        headers=setup_data["headers"],
    )

    assert patch_resp.status_code == 400
    assert "Receitas não podem receber baixa" in patch_resp.json()["detail"]


def test_fiscal_lock_blocks_modifications(client, setup_data):
    """Testa de ponta-a-ponta o ciclo de Fechamento Fiscal."""
    today = date.today()

    payload = {
        "kind": "EXPENSE",
        "occurred_on": str(today),
        "amount": 200.00,
        "description": "Conta de Luz",
        "category_id": setup_data["cat_exp_id"],
        "payment_method": "PIX",
    }
    tx_resp = client.post(
        "/api/v1/transactions", json=payload, headers=setup_data["headers"]
    )
    tx_id = tx_resp.json()["id"]

    close_resp = client.post(
        f"/api/v1/fiscal/{today.year}/{today.month}/close",
        headers=setup_data["headers"],
    )
    assert close_resp.status_code == 200

    del_resp = client.delete(
        f"/api/v1/transactions/{tx_id}", headers=setup_data["headers"]
    )
    assert del_resp.status_code == 409
    assert "closed" in del_resp.json()["detail"].lower()

    patch_resp = client.patch(
        f"/api/v1/transactions/{tx_id}",
        json={"amount": 250.00},
        headers=setup_data["headers"],
    )
    assert patch_resp.status_code == 409

    reopen_resp = client.post(
        f"/api/v1/fiscal/{today.year}/{today.month}/reopen",
        headers=setup_data["headers"],
    )
    assert reopen_resp.status_code == 200

    del_resp_2 = client.delete(
        f"/api/v1/transactions/{tx_id}", headers=setup_data["headers"]
    )
    assert del_resp_2.status_code == 200
