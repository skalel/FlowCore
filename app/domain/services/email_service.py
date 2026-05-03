import os

from jinja2 import Template

from app.config.settings import settings
from app.infra.integrations.email import EmailToSend, send_email


def render_template(template_name: str, context: dict) -> str:
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    template_path = os.path.join(
        base_dir, "templates", "emails", f"{template_name}.html"
    )

    with open(template_path, "r", encoding="utf-8") as f:
        template_string = f.read()

    template = Template(template_string)
    return template.render(context)


def send_invite_email(
    to_email: str, inviter_name: str, env_name: str, token: str, expires_at: str
):
    invite_link = f"{settings.FRONTEND_URL}/invite/accept?token={token}"

    html_content = render_template(
        "invite-email",
        {
            "env_name": env_name,
            "invite_link": invite_link,
            "inviter_name": inviter_name,
            "expires_at": expires_at,
        },
    )

    msg = EmailToSend(
        to=to_email,
        subject=f"{inviter_name} convidou-o para o ambiente {env_name}",
        html=html_content,
    )

    send_email(msg)


def send_password_reset_email(to_email: str, user_name: str, token: str):
    """
    Envia o e-mail de recuperação de senha com o link temporário.
    """
    reset_link = f"{settings.FRONTEND_URL}/reset-password?token={token}"

    html_content = render_template(
        "reset-password-email", {"user_name": user_name, "reset_link": reset_link}
    )

    msg = EmailToSend(
        to=to_email, subject="Redefinição de Senha - FlowSpace", html=html_content
    )

    send_email(msg)
