"""Dünner SMTP-Versand-Wrapper für Password-Reset-E-Mails (Forgot-Password-
Flow).

Mirrort exakt die ``accounts/spotify_oauth_client.py``-Konvention: reine
I/O-Funktion ohne DB-Zugriff, damit sie in Router-Tests komplett gemockt
werden kann (``monkeypatch.setattr(email_sender, "send_password_reset_email",
...)``) statt echte SMTP-Verbindungen aufzubauen.

Nutzt bewusst nur die Standardbibliothek (``smtplib``/``email.mime``) - es
gibt im Projekt noch keine andere E-Mail-Nutzung, die eine zusätzliche
Abhängigkeit rechtfertigen würde. Verbindungsfehler werden hier NICHT
abgefangen (das übernimmt der Call-Site im Router, siehe
``backend/app/routers/auth.py`` - ein SMTP-Fehler darf niemals die
Account-Existenz über eine unterschiedliche Response/Fehlermeldung
verraten)."""

from __future__ import annotations

import smtplib
from email.mime.text import MIMEText

from backend.app.core.config import settings


def send_password_reset_email(to_email: str, reset_link: str) -> None:
    body = (
        "Hello,\n\n"
        "We received a request to reset your Party Planning account password.\n"
        f"Use the link below within 30 minutes to choose a new password:\n\n{reset_link}\n\n"
        "If you didn't request this, you can safely ignore this email.\n"
    )
    message = MIMEText(body, "plain", "utf-8")
    message["Subject"] = "Reset your Party Planning password"
    message["From"] = settings.smtp_from_email
    message["To"] = to_email

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
        server.starttls()
        server.login(settings.smtp_username, settings.smtp_password)
        server.sendmail(settings.smtp_from_email, [to_email], message.as_string())


def send_verification_email(to_email: str, verify_link: str) -> None:
    body = (
        "Hello,\n\n"
        "Thanks for signing up for Party Planning! Please confirm this is your email address "
        f"by using the link below within 24 hours:\n\n{verify_link}\n\n"
        "If you didn't create this account, you can safely ignore this email.\n"
    )
    message = MIMEText(body, "plain", "utf-8")
    message["Subject"] = "Verify your Party Planning email address"
    message["From"] = settings.smtp_from_email
    message["To"] = to_email

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
        server.starttls()
        server.login(settings.smtp_username, settings.smtp_password)
        server.sendmail(settings.smtp_from_email, [to_email], message.as_string())


def send_account_unlock_email(to_email: str, unlock_link: str) -> None:
    body = (
        "Hello,\n\n"
        "Your Party Planning account has been blocked due to repeated failed login attempts.\n"
        f"Use the link below within 30 minutes to unlock your account:\n\n{unlock_link}\n\n"
        "If you didn't attempt to log in, you can safely ignore this email - your account "
        "stays blocked until you use this link.\n"
    )
    message = MIMEText(body, "plain", "utf-8")
    message["Subject"] = "Unlock your Party Planning account"
    message["From"] = settings.smtp_from_email
    message["To"] = to_email

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
        server.starttls()
        server.login(settings.smtp_username, settings.smtp_password)
        server.sendmail(settings.smtp_from_email, [to_email], message.as_string())
