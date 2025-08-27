import os
import ssl
import smtplib
import mimetypes
from email.message import EmailMessage
import requests

# ---- Config (can move to env vars in production) ----
EMAIL_CFG = {
    "ENABLED": True,  # False to disable email sending
    "SMTP_HOST": "smtp.gmail.com",
    "SMTP_PORT": 465,
    "SMTP_USER": "reports@yourdomain.com",
    "SMTP_PASS": "app-password-or-token",
    "FROM": "reports@yourdomain.com",
    "TO": [
        "ceo1@yourdomain.com",
        "ceo2@yourdomain.com",
        "accounting.head@yourdomain.com",
        "admin.finance@yourdomain.com"
    ],
    "SUBJECT": "CEO – Must Contact Report",
}

TELEGRAM_CFG = {
    "ENABLED": False,  # True to send via Telegram
    "BOT_TOKEN": "123456789:ABCDEF_your_bot_token",
    "CHAT_ID": "-1001234567890",  # channel/group/user chat id
}


def send_email_with_attachment(pdf_path: str, subject: str = None):
    """Send a PDF file via email."""
    if not EMAIL_CFG.get("ENABLED"):
        return

    subject = subject or EMAIL_CFG["SUBJECT"]
    msg = EmailMessage()
    msg["From"] = EMAIL_CFG["FROM"]
    msg["To"] = ", ".join(EMAIL_CFG["TO"])
    msg["Subject"] = subject
    msg.set_content("Attached: CEO – Must Contact Report")

    ctype, _ = mimetypes.guess_type(pdf_path)
    maintype, subtype = (ctype or "application/pdf").split("/")

    with open(pdf_path, "rb") as f:
        msg.add_attachment(
            f.read(),
            maintype=maintype,
            subtype=subtype,
            filename=os.path.basename(pdf_path)
        )

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(
        EMAIL_CFG["SMTP_HOST"], EMAIL_CFG["SMTP_PORT"], context=context
    ) as server:
        server.login(EMAIL_CFG["SMTP_USER"], EMAIL_CFG["SMTP_PASS"])
        server.send_message(msg)


def send_telegram_document(pdf_path: str, caption: str = None):
    """Send a PDF file via Telegram."""
    if not TELEGRAM_CFG.get("ENABLED"):
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_CFG['BOT_TOKEN']}/sendDocument"
    with open(pdf_path, "rb") as f:
        files = {"document": (os.path.basename(pdf_path), f, "application/pdf")}
        data = {
            "chat_id": TELEGRAM_CFG["CHAT_ID"],
            "caption": caption or "CEO – Must Contact Report"
        }
        r = requests.post(url, data=data, files=files, timeout=30)
        r.raise_for_status()