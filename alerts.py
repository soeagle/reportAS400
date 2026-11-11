"""Allarmi email e storico (tracciabilità NIS2)."""

import json
import os
import smtplib
from datetime import datetime
from email.mime.text import MIMEText

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE = os.path.join(BASE_DIR, "alarms_history.jsonl")


def record_alarms(checks):
    """Scrive gli allarmi correnti nello storico JSONL (evidenze NIS2)."""
    ts = datetime.now().isoformat(timespec="seconds")
    with open(HISTORY_FILE, "a", encoding="utf-8") as fh:
        for c in checks:
            if c["status"] == "ALLARME":
                fh.write(json.dumps({"ts": ts, **c}, ensure_ascii=False) + "\n")


def read_history(limit=500):
    if not os.path.exists(HISTORY_FILE):
        return []
    with open(HISTORY_FILE, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh.readlines()[-limit:]]


def send_alarm_email(cfg, checks):
    """Invia un'email quando qualcosa non va (come da screenshot)."""
    mail = cfg.get("email", {})
    if not mail.get("enabled"):
        return False
    alarms = [c for c in checks if c["status"] == "ALLARME"]
    if not alarms:
        return False
    body = ["Allarmi TwgIBMiControl", ""]
    for c in alarms:
        body.append(f"[{c['severity'].upper()}] {c['name']}: {c['value']}")
        if c["detail"]:
            body.append(f"    {c['detail']}")
    msg = MIMEText("\n".join(body), "plain", "utf-8")
    msg["Subject"] = f"[TwgIBMiControl] {len(alarms)} allarmi su IBM i"
    msg["From"] = mail["from"]
    msg["To"] = ", ".join(mail["to"])
    with smtplib.SMTP(mail["smtp_host"], mail["smtp_port"]) as s:
        s.starttls()
        if mail.get("smtp_user"):
            s.login(mail["smtp_user"], mail.get("smtp_password", ""))
        s.send_message(msg)
    return True
