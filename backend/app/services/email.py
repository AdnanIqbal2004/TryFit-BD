"""Transactional email delivery with local development link previews."""
from email.message import EmailMessage
import smtplib
from urllib.parse import quote

from app.core.config import Settings

def action_link(settings: Settings, action: str, token: str) -> str:
    return f"{settings.app_base_url.rstrip('/')}/#{action}?token={quote(token)}"

def send_action_email(settings: Settings, to: str, subject: str, link: str) -> str | None:
    if not settings.smtp_host:
        if settings.env.lower() == "development":
            return link
        raise RuntimeError("Email delivery is not configured.")
    message = EmailMessage()
    message["Subject"], message["From"], message["To"] = subject, settings.smtp_sender, to
    message.set_content(f"Use this secure link to continue: {link}\n\nIf you did not request this, ignore this message.")
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
        if settings.smtp_starttls:
            server.starttls()
        if settings.smtp_username:
            server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(message)
    return None
