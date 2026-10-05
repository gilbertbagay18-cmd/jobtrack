import os
import smtplib
import ssl
from email.message import EmailMessage

def send_email(to, subject, body):
    server = os.environ.get("MAIL_SERVER")
    if not server:
        print("\n[DEV MODE] Email not configured. Message for " + to + ":\n" + body + "\n", flush=True)
        return False
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.environ.get("MAIL_DEFAULT_SENDER") or os.environ.get("MAIL_USERNAME")
    msg["To"] = to
    msg.set_content(body)
    port = int(os.environ.get("MAIL_PORT", "587"))
    try:
        with smtplib.SMTP(server, port, timeout=15) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(os.environ["MAIL_USERNAME"], os.environ["MAIL_PASSWORD"])
            smtp.send_message(msg)
        return True
    except Exception as err:
        print("Email failed:", err, flush=True)
        return False
