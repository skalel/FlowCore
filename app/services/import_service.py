import io
import re
import uuid
from datetime import datetime

import pandas as pd
import sqlalchemy as sa
from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import Session

from app.infra.db.orm_models import (
    Card,
    Category,
    FiscalClosure,
    ImportTask,
    Installment,
    InstallmentOccurrence,
    Transaction,
)
from app.infra.db.session import SessionLocal
from app.services.ai_service import classify_transactions_with_toon


def parse_installment_from_description(description: str):
    """
    Identifica se a descrição contém padrão de parcelamento. Ex: "Geladeira (2/10)"
    Retorna: (Titulo_Limpo, Parcela_Atual, Total_Parcelas)
    """
    if not isinstance(description, str):
        return str(description), 1, 1

    match = re.search(r"[\(\[]?(\d+)[/| de ](\d+)[\)\]]?", description)

    if match:
        current_inst = int(match.group(1))
        total_inst = int(match.group(2))
        clean_title = re.sub(
            r"\s*[\(\[]?\d+[/| de ]\d+[\)\]]?\s*", "", description
        ).strip()
        return clean_title, current_inst, total_inst

    return description.strip(), 1, 1


def process_import_in_background(
    task_id: str,
    file_contents: bytes,
    filename: str,
    env_id: uuid.UUID,
    user_id: uuid.UUID,
):
    """
    Função pesada que roda em segundo plano para não travar a API do usuário.
    """
    db: Session = SessionLocal()

    task = db.get(ImportTask, uuid.UUID(task_id))
    if not task:
        db.close()
        return

    print(f"[{task_id}] Iniciando processamento do arquivo: {filename}")

    try:
        if filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(file_contents))
        elif filename.endswith(".xlsx"):
            df = pd.read_excel(io.BytesIO(file_contents))
        else:
            print(f"[{task_id}] Formato não suportado.")
            return
    except Exception as e:
        print(f"[{task_id}] Erro ao ler planilha: {e}")
        return

    df.columns = df.columns.str.strip().str.lower()
    df = df.where(pd.notnull(df), None)
    records = df.to_dict("records")

    created_count = 0
    transactions_for_ai = []

    try:
        for row in records:
            raw_data = row.get("data")
            raw_valor = row.get("valor")

            if raw_data is None or raw_valor is None:
                continue

            amount = abs(float(raw_valor or 0.0))
            occurred_on = pd.to_datetime(str(raw_data)).date()
            raw_desc = str(row.get("descricao") or "Sem Descrição").strip()
            kind = str(row.get("tipo") or "EXPENSE").strip().upper()
            pay_method = str(row.get("metodo_pagamento") or "OTHER").strip().upper()

            title, curr_inst, tot_inst = parse_installment_from_description(raw_desc)

            cat_name = str(row.get("categoria", "Importados")).strip()
            if cat_name.lower() == "nan":
                cat_name = "Importados"

            category = db.execute(
                sa.select(Category).where(
                    Category.environment_id == env_id,
                    sa.func.lower(Category.name) == cat_name.lower(),
                )
            ).scalar_one_or_none()

            if not category:
                category = Category(environment_id=env_id, name=cat_name, kind=kind)
                db.add(category)
                db.flush()

            card_id = None
            raw_last4 = str(row.get("final_cartao", "")).strip()

            if pay_method == "CREDIT" and raw_last4 and raw_last4.lower() != "nan":
                last4 = raw_last4.split(".")[0][-4:].zfill(4)
                card = db.execute(
                    sa.select(Card).where(
                        Card.environment_id == env_id, Card.last4 == last4
                    )
                ).scalar_one_or_none()
                if not card:
                    card = Card(
                        environment_id=env_id,
                        last4=last4,
                        description="Cartão Importado (Pendente)",
                        due_day=1,
                        pay_day=10,
                        holder_id=None,
                        created_by_user_id=user_id,
                    )
                    db.add(card)
                    db.flush()
                card_id = card.id

            if tot_inst == 1:
                _unlock_fiscal_month(db, env_id, user_id, occurred_on)

                tx = Transaction(
                    environment_id=env_id,
                    created_by_user_id=user_id,
                    kind=kind,
                    occurred_on=occurred_on,
                    due_on=occurred_on,
                    amount=amount,
                    description=title,
                    category_id=category.id,
                    payment_method=pay_method,
                    card_id=card_id,
                    paid_on=occurred_on if pay_method != "CREDIT" else None,
                )
                db.add(tx)

                if cat_name.lower() == "importados":
                    transactions_for_ai.append(tx)
            else:
                total_amount = amount * tot_inst
                first_due = occurred_on - relativedelta(months=(curr_inst - 1))
                inst = Installment(
                    environment_id=env_id,
                    kind="PURCHASE",
                    title=title,
                    principal_amount=total_amount,
                    total_installments=tot_inst,
                    installment_amount=amount,
                    first_due_on=first_due,
                    current_installment=curr_inst,
                    card_id=card_id,
                    created_by_user_id=user_id,
                )
                db.add(inst)
                db.flush()

                for i in range(1, tot_inst + 1):
                    occ_due = first_due + relativedelta(months=(i - 1))
                    _unlock_fiscal_month(db, env_id, user_id, occ_due)
                    tx = Transaction(
                        environment_id=env_id,
                        created_by_user_id=user_id,
                        kind=kind,
                        occurred_on=occurred_on,
                        due_on=occ_due,
                        amount=amount,
                        description=f"{title} ({i}/{tot_inst})",
                        category_id=category.id,
                        payment_method=pay_method,
                        card_id=card_id,
                        installment_id=inst.id,
                        paid_on=occ_due if i < curr_inst else None,
                    )
                    db.add(tx)
                    db.flush()
                    db.add(
                        InstallmentOccurrence(
                            installment_id=inst.id,
                            installment_number=i,
                            due_on=occ_due,
                            transaction_id=tx.id,
                        )
                    )

                    if cat_name.lower() == "importados":
                        transactions_for_ai.append(tx)

            created_count += 1

        try:
            db.flush()

            if transactions_for_ai:
                all_cats = (
                    db.execute(
                        sa.select(Category).where(Category.environment_id == env_id)
                    )
                    .scalars()
                    .all()
                )

                cat_map = {"INCOME": [], "EXPENSE": []}
                for c in all_cats:
                    if c.kind in cat_map:
                        cat_map[c.kind].append(c.name)

                batch_to_classify = [
                    {
                        "id": str(tx.id),
                        "desc": tx.description,
                        "amount": float(tx.amount),
                        "kind": tx.kind,
                    }
                    for tx in transactions_for_ai
                ]

                print(
                    f"[{task_id}] IA: Analisando {len(batch_to_classify)} transações via TOON..."
                )

                classifications = classify_transactions_with_toon(
                    batch_to_classify, cat_map
                )
                print(f"[{task_id}] IA: Resposta recebida! {classifications}")

                for tx in transactions_for_ai:
                    suggested_name = classifications.get(str(tx.id))

                    if suggested_name and suggested_name.lower() != "outros":
                        cat_ia = db.execute(
                            sa.select(Category).where(
                                Category.environment_id == env_id,
                                sa.func.lower(Category.name) == suggested_name.lower(),
                                Category.kind == tx.kind,
                            )
                        ).scalar_one_or_none()

                        if not cat_ia:
                            cat_ia = Category(
                                environment_id=env_id,
                                name=suggested_name,
                                kind=tx.kind,
                                owner_user_id=user_id,
                            )
                            db.add(cat_ia)
                            db.flush()

                        tx.category_id = cat_ia.id

        except Exception as ai_error:
            print(f"[{task_id}] Aviso: Falha não-crítica na IA. Motivo: {ai_error}")

        db.commit()
        task.status = "COMPLETED"
        print(
            f"[{task_id}] Importação concluída! {created_count} registros processados."
        )

    except Exception as e:
        db.rollback()
        task.status = "FAILED"
        task.error_message = str(e)
        print(
            f"[{task_id}] Erro crítico na importação. Rollback efetuado. Motivo: {str(e)}"
        )
    finally:
        db.commit()
        db.close()


def _unlock_fiscal_month(
    db: Session, env_id: uuid.UUID, user_id: uuid.UUID, target_date
):
    """
    Destranca um mês fiscal silenciosamente se ele estiver fechado.
    """
    closure = db.execute(
        sa.select(FiscalClosure).where(
            FiscalClosure.environment_id == env_id,
            FiscalClosure.year == target_date.year,
            FiscalClosure.month == target_date.month,
            FiscalClosure.status == "CLOSED",
        )
    ).scalar_one_or_none()

    if closure:
        closure.status = "OPEN"
        db.execute(
            sa.text("""
            INSERT INTO audit_log (id, environment_id, actor_user_id, action, entity_type, entity_id)
            VALUES (gen_random_uuid(), :eid, :uid, 'FISCAL_AUTO_REOPEN', 'fiscal_closures', :cid)
        """),
            {"eid": str(env_id), "uid": str(user_id), "cid": str(closure.id)},
        )
