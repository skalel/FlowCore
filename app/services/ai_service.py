import json
import re

# from google import genai
# from google.genai import types
from openai import OpenAI

from app.config.settings import settings


def classify_transactions_with_toon(
    transactions: list[dict], categories_by_kind: dict[str, list[str]]
) -> dict[str, str]:
    if not transactions:
        return {}

    unique_requests = {}
    for tx in transactions:
        base_desc = re.sub(r"\s*\(\d+/\d+\)$", "", tx["desc"]).strip()
        key = (base_desc, tx["kind"].strip())

        if key not in unique_requests:
            unique_requests[key] = []
        unique_requests[key].append(tx["id"])

    count = len(unique_requests)

    income_cats = ", ".join(categories_by_kind.get("INCOME", []))
    expense_cats = ", ".join(categories_by_kind.get("EXPENSE", []))

    toon_payload = f"transactions[{count}]{{id,description,type}}:\n"
    temp_id_to_real_ids = {}

    for i, (key, real_ids) in enumerate(unique_requests.items(), start=1):
        temp_id = str(i)
        temp_id_to_real_ids[temp_id] = real_ids

        desc, kind = key
        clean_desc = desc.replace(",", " ").strip()
        toon_payload += f"  {temp_id},{clean_desc},{kind}\n"

    system_instruction = f"""Classify financial transactions based strictly on their 'type'.
      Allowed INCOME categories: {income_cats}
      Allowed EXPENSE categories: {expense_cats}

      Strict rules:
      1. If type is INCOME, you MUST pick from INCOME categories.
      2. If type is EXPENSE, you MUST pick from EXPENSE categories.
      3. Respond ONLY using TOON format: results[{count}]{{id,category}}:
      4. You MUST return exactly {count} rows. Do NOT skip any ID.
      5. No markdown, no explanations.
      6. Respond only in Brazilian Portuguese.
      7. Create a new category if none fit."""

    try:
        # client = genai.Client(api_key=settings.GEMINI_API_KEY)
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.OPENROUTER_API_KEY,
        )

        print(f"[{count} requisições únicas] Payload enviado para IA:\n{toon_payload}")

        response = client.chat.completions.create(
            model="openai/gpt-oss-120b:free",
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": toon_payload},
            ],
            temperature=0.0,
            max_tokens=1500,
            extra_headers={"HTTP-Referer": settings.FRONTEND_URL, "X-Title": "FinAPI"},
        )

        raw_text = response.choices[0].message.content.strip()
        print(f"Resposta Crua da IA:\n{raw_text}")

        result_map = {}
        for line in raw_text.split("\n"):
            line = line.strip()
            if (
                not line
                or line.startswith("results[")
                or line.startswith("}")
                or line.startswith("```")
            ):
                continue

            parts = line.split(",")
            if len(parts) >= 2:
                temp_id = parts[0].strip()
                category = parts[1].strip()

                if temp_id in temp_id_to_real_ids:
                    for real_uuid in temp_id_to_real_ids[temp_id]:
                        result_map[real_uuid] = category

        return result_map

    except Exception as e:
        print(f"Erro na Classificação por IA: {e}")
        return {}


def suggest_single_category(
    description: str, kind: str, existing_categories: list[str]
) -> str:
    """Retorna apenas o nome de uma categoria sugerida para uma descrição em tempo real."""
    if not description or len(description) < 3:
        return ""

    cats_str = ", ".join(existing_categories)

    system_instruction = f"""Classify a single financial transaction description.
      Type: {kind}
      Allowed Categories: {cats_str}

      Rules:
      1. Respond ONLY with the category name. No markdown, no quotes, no explanations.
      2. If it matches an Allowed Category perfectly, use it.
      3. If not, suggest a short, common category name in Brazilian Portuguese."""

    try:
        # // Padrão Gemini
        #
        # client = genai.Client(api_key=settings.GEMINI_API_KEY)
        # response = client.models.generate_content(
        #     model="gemini-2.5-flash",
        #     contents=description,
        #     config=types.GenerateContentConfig(
        #         system_instruction=system_instruction,
        #         temperature=0.0,
        #         max_output_tokens=10, # Bloqueia qualquer alucinação longa
        #     ),
        # )
        #
        # return response.text.strip()

        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.OPENROUTER_API_KEY,
        )

        response = client.chat.completions.create(
            model="openai/gpt-oss-120b:free",
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": description},
            ],
            temperature=0.0,
            max_tokens=10,
            extra_headers={"HTTP-Referer": settings.FRONTEND_URL, "X-Title": "FinAPI"},
        )

        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Erro IA Realtime: {e}")
        return ""


def generate_financial_analysis(transactions: list[dict]) -> dict | None:
    """
    Recebe um lote de transações dos últimos 3 meses e retorna uma análise comportamental.
    """
    if not transactions:
        return None

    count = len(transactions)

    toon_payload = f"transactions[{count}]{{date,description,amount,type,category}}:\n"
    for tx in transactions:
        clean_desc = tx["description"].replace(",", " ").strip()
        toon_payload += f"  {tx['date']},{clean_desc},{tx['amount']},{tx['kind']},{tx['category']}\n"

    system_instruction = """Você é um conselheiro financeiro de elite. Analise os últimos 3 meses de transações enviadas no formato TOON.

    Regras Estritas:
    1. NÃO repita a soma das categorias ou do saldo (o usuário já possui gráficos para isso).
    2. Foque apenas em comportamentos, tendências e alertas (Ex: "Seus gastos com delivery aumentam drasticamente nas sextas-feiras").
    3. Tente identificar gastos fantasmas, impulsos ou assinaturas desnecessárias.
    4. Responda em Português do Brasil.
    5. Você DEVE responder ESTRITAMENTE um JSON válido. Sem formatação markdown, sem blocos ```json. APENAS o objeto JSON.

    Formato Obrigatório:
    {
      "summary": "Resumo amigável e direto de 2 linhas sobre o comportamento financeiro do período.",
      "alerts": ["Alerta prático 1", "Alerta prático 2"],
      "praise": "Um elogio sobre algum bom hábito financeiro identificado (se houver)",
      "action_plan": "Um passo prático, claro e direto para o próximo mês."
    }"""

    try:
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.OPENROUTER_API_KEY,
        )

        print(f"Enviando {count} transações para análise trimestral via OpenRouter...")

        response = client.chat.completions.create(
            model="openai/gpt-oss-120b:free",
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": toon_payload},
            ],
            temperature=0.2,
            max_tokens=1500,
        )

        raw_text = response.choices[0].message.content.strip()

        if raw_text.startswith("```json"):
            raw_text = raw_text[7:-3].strip()
        elif raw_text.startswith("```"):
            raw_text = raw_text[3:-3].strip()

        return json.loads(raw_text)

    except Exception as e:
        print(f"Erro na Análise Financeira (OpenRouter): {e}")
        return None
