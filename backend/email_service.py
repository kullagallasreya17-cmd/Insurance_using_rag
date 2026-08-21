import logging
import os
import smtplib
from email.message import EmailMessage


def smtp_configuration() -> dict:
    """Return non-secret SMTP configuration status for diagnostics."""
    host = os.getenv("SMTP_HOST", "").strip()
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    sender = os.getenv("SMTP_FROM_EMAIL", "").strip() or username
    port = int(os.getenv("SMTP_PORT", "587"))
    security = os.getenv("SMTP_SECURITY", "").strip().lower()
    if not security:
        legacy_tls = os.getenv("SMTP_USE_TLS")
        if legacy_tls is not None:
            security = "starttls" if legacy_tls.lower() == "true" else "none"
        else:
            security = "ssl" if port == 465 else "starttls"

    missing = []
    if not host:
        missing.append("SMTP_HOST")
    if not sender:
        missing.append("SMTP_FROM_EMAIL or SMTP_USERNAME")
    if bool(username) != bool(password):
        missing.append("SMTP_USERNAME and SMTP_PASSWORD must be provided together")
    if security not in {"starttls", "ssl", "none"}:
        missing.append("SMTP_SECURITY must be starttls, ssl, or none")

    return {
        "configured": not missing,
        "host": host,
        "port": port,
        "security": security,
        "sender_configured": bool(sender),
        "authentication_configured": bool(username and password),
        "missing": missing,
    }


def send_email(recipient: str, subject: str, text: str, html: str | None = None) -> None:
    config = smtp_configuration()
    if not config["configured"]:
        raise RuntimeError("SMTP email delivery is not configured: " + ", ".join(config["missing"]))

    host = config["host"]
    port = config["port"]
    security = config["security"]
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    sender = os.getenv("SMTP_FROM_EMAIL", "").strip() or username

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{os.getenv('SMTP_FROM_NAME', 'Insurance AI Platform')} <{sender}>"
    message["To"] = recipient
    message.set_content(text)
    if html:
        message.add_alternative(html, subtype="html")

    try:
        smtp_class = smtplib.SMTP_SSL if security == "ssl" else smtplib.SMTP
        with smtp_class(host, port, timeout=20) as smtp:
            smtp.ehlo()
            if security == "starttls":
                smtp.starttls()
                smtp.ehlo()
            if username:
                smtp.login(username, password or "")
            smtp.send_message(message)
    except Exception:
        logging.exception("Email delivery failed for configured recipient")
        raise