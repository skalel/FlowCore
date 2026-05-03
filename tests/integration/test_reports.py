from datetime import date, timedelta

import pytest


@pytest.fixture
def report_data(client):
    """Prepara um cenário financeiro exato para testarmos a matemática do relatório."""

    env_resp = client.post(
        "/api/v1/environments", json={"type": "FAMILY", "name": "Env Dashboard"}
    )
    assert env_resp.status_code == 200
    env_id = env_resp.json()["id"]
    headers = {"X-Environment-Id": env_id}

    cat_exp = client.post(
        "/api/v1/categories",
        json={"name": "Moradia", "kind": "EXPENSE"},
        headers=headers,
    ).json()["id"]
    cat_inc = client.post(
        "/api/v1/categories",
        json={"name": "Salário", "kind": "INCOME"},
        headers=headers,
    ).json()["id"]

    today = date.today()
    yesterday = today - timedelta(days=1)

    client.post(
        "/api/v1/transactions",
        json={
            "kind": "INCOME",
            "occurred_on": str(today),
            "amount": 5000.00,
            "description": "Salário Mensal",
            "category_id": cat_inc,
            "payment_method": "PIX",
        },
        headers=headers,
    )

    tx_paga = client.post(
        "/api/v1/transactions",
        json={
            "kind": "EXPENSE",
            "occurred_on": str(today),
            "amount": 1000.00,
            "description": "Aluguel",
            "category_id": cat_exp,
            "payment_method": "PIX",
        },
        headers=headers,
    ).json()

    client.patch(
        f"/api/v1/transactions/{tx_paga['id']}",
        json={"paid_on": str(today)},
        headers=headers,
    )

    client.post(
        "/api/v1/transactions",
        json={
            "kind": "EXPENSE",
            "occurred_on": str(yesterday),
            "due_on": str(yesterday),
            "amount": 500.00,
            "description": "Condomínio",
            "category_id": cat_exp,
            "payment_method": "PIX",
        },
        headers=headers,
    )

    return {
        "env_id": env_id,
        "headers": headers,
        "year": today.year,
        "month": today.month,
    }


def test_monthly_report_math_and_aggregations(client, report_data):
    """Verifica se o relatório soma receitas, despesas, calcula o saldo e acha as pendências corretamente."""

    response = client.get(
        f"/api/v1/reports/monthly?year={report_data['year']}&month={report_data['month']}",
        headers=report_data["headers"],
    )

    assert response.status_code == 200
    data = response.json()

    assert data["total_income"] == 5000.00
    assert data["total_expense"] == 1500.00
    assert data["balance"] == 3500.00

    assert data["pending_count"] == 1
    assert data["pending_total"] == 500.00

    assert len(data["by_category_expense"]) >= 1
    assert data["by_category_expense"][0]["total"] == 1500.00


def test_monthly_report_reflects_fiscal_closure(client, report_data):
    """Verifica se o endpoint do Dashboard avisa corretamente que o mês foi fechado."""

    headers = report_data["headers"]
    y = report_data["year"]
    m = report_data["month"]

    resp_open = client.get(
        f"/api/v1/reports/monthly?year={y}&month={m}", headers=headers
    )
    assert resp_open.json()["is_closed"] is False

    client.post(f"/api/v1/fiscal/{y}/{m}/close", headers=headers)

    resp_closed = client.get(
        f"/api/v1/reports/monthly?year={y}&month={m}", headers=headers
    )
    assert resp_closed.json()["is_closed"] is True
