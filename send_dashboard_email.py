#!/usr/bin/env python3
"""
send_dashboard_email.py — Export data dashboard lalu kirim sebagai
attachment email, biar bisa langsung diunduh dari HP tanpa file manager.

Usage:
    python3 send_dashboard_email.py
"""
import subprocess
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import os

from config import EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECEIVER

def main():
    print("Generating dashboard_export.json ...")
    result = subprocess.run(
        ["python3", "export_dashboard_data.py"],
        capture_output=True, text=True
    )
    print(result.stdout)
    if result.returncode != 0:
        print("Export gagal:", result.stderr)
        return

    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard_export.json")
    if not os.path.exists(json_path):
        print("File dashboard_export.json tidak ditemukan setelah export.")
        return

    msg = MIMEMultipart()
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER
    msg["Subject"] = "AI Scanner — Dashboard Export"
    msg.attach(MIMEText(
        "Dashboard data terlampir. Buka dashboard artifact di Claude, "
        "lalu upload file dashboard_export.json yang ada di attachment email ini.",
        "plain"
    ))

    with open(json_path, "rb") as f:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", "attachment", filename="dashboard_export.json")
    msg.attach(part)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as srv:
            srv.login(EMAIL_SENDER, EMAIL_PASSWORD)
            srv.send_message(msg)
        print("Email terkirim dengan attachment dashboard_export.json")
    except smtplib.SMTPAuthenticationError:
        print("Gmail auth gagal — cek App Password di config.py")
    except Exception as e:
        print(f"Gagal kirim email: {e}")


if __name__ == "__main__":
    main()
