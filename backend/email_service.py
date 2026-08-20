import logging
import os
import smtplib
from email.message import EmailMessage


def send_email(recipient: str, subject: str, text: str, html: str | None = None) -> None:
    host = os.getenv("SMTP_HOST")
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    sender = os.getenv("SMTP_FROM_EMAIL")
    if not all((host, sender)):
        raise RuntimeError("SMTP email delivery is not configured")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{os.getenv('SMTP_FROM_NAME', 'Insurance AI Platform')} <{sender}>"
    message["To"] = recipient
    message.set_content(text)
    if html:
        message.add_alternative(html, subtype="html")

    port = int(os.getenv("SMTP_PORT", "587"))
    try:
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            smtp.ehlo()
            if os.getenv("SMTP_USE_TLS", "true").lower() == "true":
                smtp.starttls()
                smtp.ehlo()
            if username:
                smtp.login(username, password or "")
            smtp.send_message(message)
    except Exception:
        logging.exception("Email delivery failed for configured recipient")
        raise