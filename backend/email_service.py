import logging
import os
import smtplib
from email.message import EmailMessage
from urllib.parse import quote


logger = logging.getLogger(__name__)


def _send_email(recipient: str, subject: str, text: str, html: str) -> None:
    host = os.getenv("SMTP_HOST", "").strip()
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    sender = os.getenv("SMTP_FROM_EMAIL", username).strip()
    if not host or not sender:
        raise RuntimeError("Email delivery is not configured")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{os.getenv('SMTP_FROM_NAME', 'Insurance AI Platform')} <{sender}>"
    message["To"] = recipient
    message.set_content(text)
    message.add_alternative(html, subtype="html")
    port = int(os.getenv("SMTP_PORT", "587"))
    smtp_class = smtplib.SMTP_SSL if port == 465 else smtplib.SMTP
    with smtp_class(host, port, timeout=15) as smtp:
        if port != 465:
            smtp.starttls()
        if username:
            smtp.login(username, password)
        smtp.send_message(message)


def send_verification_email(email: str, token: str) -> None:
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")
    link = f"{frontend_url}/verify-email?token={quote(token)}"
    _send_email(email, "Verify your Insurance AI Platform email", f"Verify your email: {link}", f"<p>Verify your Insurance AI Platform email.</p><p><a href='{link}'>Verify email</a></p><p>This link expires shortly.</p>")


def send_reset_email(email: str, token: str) -> None:
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")
    link = f"{frontend_url}/reset-password?token={quote(token)}"
    _send_email(email, "Reset your Insurance AI Platform password", f"Create a new password: {link}", f"<p>We received a request to reset your password.</p><p><a href='{link}'>Reset Password</a></p><p>This link expires shortly and can only be used once.</p><p>If you did not request this, you can safely ignore this email.</p>")