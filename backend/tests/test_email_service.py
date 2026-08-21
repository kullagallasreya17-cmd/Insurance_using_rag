import smtplib

import pytest

from email_service import send_email, smtp_configuration


def test_smtp_configuration_requires_authentication_pair(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USERNAME", "user@example.com")
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    monkeypatch.delenv("SMTP_FROM_EMAIL", raising=False)

    config = smtp_configuration()

    assert config["configured"] is False
    assert "SMTP_USERNAME and SMTP_PASSWORD must be provided together" in config["missing"]


def test_send_email_uses_ssl_for_port_465(monkeypatch):
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            calls.append((host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def ehlo(self):
            calls.append("ehlo")

        def login(self, username, password):
            calls.append(("login", username, password))

        def send_message(self, message):
            calls.append(("send", message["From"], message["To"]))

    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "465")
    monkeypatch.setenv("SMTP_USERNAME", "user@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password")
    monkeypatch.delenv("SMTP_FROM_EMAIL", raising=False)
    monkeypatch.delenv("SMTP_SECURITY", raising=False)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)

    send_email("recipient@example.com", "Subject", "Body")

    assert calls[0] == ("smtp.example.com", 465, 20)
    assert "ehlo" in calls
    assert ("login", "user@example.com", "app-password") in calls
    assert ("send", "Insurance AI Platform <user@example.com>", "recipient@example.com") in calls


def test_send_email_uses_starttls_for_port_587(monkeypatch):
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            calls.append((host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def ehlo(self):
            calls.append("ehlo")

        def starttls(self):
            calls.append("starttls")

        def login(self, username, password):
            calls.append(("login", username, password))

        def send_message(self, _message):
            calls.append("send")

    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_SECURITY", "starttls")
    monkeypatch.setenv("SMTP_USERNAME", "user@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password")
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)

    send_email("recipient@example.com", "Subject", "Body")

    assert calls[0] == ("smtp.example.com", 587, 20)
    assert "starttls" in calls


def test_send_email_reports_missing_smtp_host(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.setenv("SMTP_USERNAME", "user@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password")

    with pytest.raises(RuntimeError, match="SMTP_HOST"):
        send_email("recipient@example.com", "Subject", "Body")
