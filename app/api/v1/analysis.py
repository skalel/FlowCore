import uuid
from datetime import datetime

import sqlalchemy as sa
from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.env_deps import get_environment_id_from_header
from app.api.perm_deps import require_permission
from app.infra.db.orm_models import Category, Transaction
from app.services.ai_service import generate_financial_analysis

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.get(
    "/insights",
    dependencies=[
        Depends(require_permission("ledger:read", get_environment_id_from_header))
    ],
)
def get_quarterly_insights(
    db: Session = Depends(get_db),
    env_id: uuid.UUID = Depends(get_environment_id_from_header),
):
    """
    Puxa os últimos 3 meses de transações e tenta gerar insights usando IA.
    Caso a IA falhe (indisponibilidade do modelo gratuito), aciona um motor
    heurístico matemático como fallback (última opção) para nunca deixar o usuário na mão.
    """
    three_months_ago = datetime.now() - relativedelta(months=3)

    transactions_db = db.execute(
        sa.select(Transaction, Category.name.label("category_name"))
        .outerjoin(Category, Transaction.category_id == Category.id)
        .where(
            Transaction.environment_id == env_id,
            Transaction.occurred_on >= three_months_ago.date(),
            Transaction.deleted_at.is_(None),
            Transaction.status == "POSTED",
        )
        .order_by(Transaction.occurred_on.asc())
    ).all()

    if not transactions_db or len(transactions_db) < 3:
        return {
            "summary": "Ainda estou aprendendo sobre seus hábitos financeiros.",
            "alerts": [
                "Você precisa registrar mais movimentações para eu identificar padrões."
            ],
            "praise": "Excelente iniciativa de começar a organizar suas finanças!",
            "action_plan": "Registre suas despesas e receitas dos próximos dias para gerarmos seu diagnóstico.",
        }

    tx_payload = []
    for tx, cat_name in transactions_db:
        tx_payload.append(
            {
                "date": tx.occurred_on.strftime("%Y-%m-%d"),
                "description": tx.description,
                "amount": float(tx.amount),
                "kind": tx.kind,
                "category": cat_name or "Outros",
            }
        )
    try:
        insights = generate_financial_analysis(tx_payload)
        if insights and isinstance(insights, dict) and "summary" in insights:
            return insights
    except Exception as e:
        print(f"[Fallback Ativado] Falha na IA externa: {str(e)}")
        pass

    total_income = 0.0
    total_expense = 0.0
    expense_by_category = {}
    small_expenses_count = 0

    for tx, cat_name in transactions_db:
        amt = float(tx.amount)
        if tx.kind == "INCOME":
            total_income += amt
        else:
            total_expense += amt
            cat = cat_name or "Outros"
            expense_by_category[cat] = expense_by_category.get(cat, 0.0) + amt

            if amt <= 30.0:
                small_expenses_count += 1

    alerts = []
    action_plan_steps = []

    if total_expense > total_income:
        deficit = total_expense - total_income
        alerts.append(
            f"Alerta vermelho: Você gastou R$ {deficit:,.2f} a mais do que arrecadou nestes 3 meses."
        )
        action_plan_steps.append(
            "Corte imediatamente gastos não essenciais até equalizar o saldo."
        )
        summary = "Seu fluxo de caixa está negativo. Precisamos ajustar a rota."
        praise = "Você tem mantido o registro ativo, o que é o primeiro passo para a recuperação."
    else:
        savings = total_income - total_expense
        savings_rate = (savings / total_income) * 100 if total_income > 0 else 0
        summary = "Seu trimestre está saudável. Você está operando no verde."
        praise = f"Incrível! Você conseguiu reter {savings_rate:.1f}% de tudo que ganhou neste período."
        action_plan_steps.append(
            "Considere investir o excedente do seu saldo para gerar renda passiva."
        )

    if expense_by_category:
        top_category = max(expense_by_category, key=lambda k: expense_by_category[k])
        top_cat_amount = expense_by_category[top_category]

        if total_expense > 0 and (top_cat_amount / total_expense) > 0.4:
            alerts.append(
                f"Concentração de risco: {top_category} representa mais de 40% dos seus gastos (R$ {top_cat_amount:,.2f})."
            )
            action_plan_steps.append(
                f"Estabeleça um teto rigoroso mensal para gastos com '{top_category}'."
            )

    if small_expenses_count > 20:
        alerts.append(
            f"Detectei {small_expenses_count} transações de baixo valor. Elas parecem inofensivas, mas drenam seu saldo."
        )
        action_plan_steps.append(
            "Revise assinaturas não utilizadas e reduza compras por impulso do dia a dia."
        )

    if not alerts:
        alerts.append("Nenhum risco grave detectado nos seus padrões recentes.")

    return {
        "summary": summary,
        "alerts": alerts,
        "praise": praise,
        "action_plan": " ".join(action_plan_steps),
    }
