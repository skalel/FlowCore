from dataclasses import dataclass
from typing import Optional

import resend

from app.config.settings import settings

resend.api_key = settings.RESEND_API_KEY


@dataclass
class EmailToSend:
    to: str
    subject: str
    text: str = ""
    html: Optional[str] = None


def send_email(msg: EmailToSend) -> dict:
    """
    Envia um e-mail através da API do Resend.
    """
    params = {
        "from": settings.EMAIL_FROM,
        "to": [msg.to],
        "subject": msg.subject,
    }

    if msg.html:
        params["html"] = msg.html
    elif msg.text:
        params["text"] = msg.text
    else:
        raise ValueError("O e-mail deve conter 'text' ou 'html'.")

    try:
        response = resend.Emails.send(params)
        return response
    except Exception as e:
        print(f"Erro crítico ao enviar e-mail via Resend para {msg.to}: {e}")
        raise e
