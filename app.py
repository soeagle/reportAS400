"""TwgIBMiControl - dashboard di monitoraggio NIS2 per IBM i (AS/400).

Avvio:  python app.py   (di default parte in demo_mode, senza AS/400)
"""

import threading
import time

from flask import Flask, jsonify, render_template, request

import alerts
import report
from checks import run_all_checks
from db import get_connection, load_config

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True

STATE = {"checks": [], "data": {}, "lock": threading.Lock()}


def refresh():
    cfg = load_config()
    conn = get_connection()
    checks, data = run_all_checks(conn, cfg)
    alerts.record_alarms(checks)
    alerts.send_alarm_email(cfg, checks)
    with STATE["lock"]:
        STATE["checks"] = checks
        STATE["data"] = data


def poller(seconds):
    while True:
        try:
            refresh()
        except Exception as exc:  # noqa: BLE001
            with STATE["lock"]:
                STATE["data"]["error"] = str(exc)
        time.sleep(seconds)


@app.context_processor
def inject_globals():
    with STATE["lock"]:
        data = dict(STATE["data"])
    return {"data": data,
            "cfg_as400": load_config()["as400"]["system"]}


@app.route("/")
def stato():
    with STATE["lock"]:
        empty = not STATE["data"].get("checks")
    if empty:
        refresh()
    with STATE["lock"]:
        data = dict(STATE["data"])
    checks = data.get("checks", [])
    return render_template("stato.html", data=data, checks=checks,
                           thresholds=load_config()["thresholds"])


@app.route("/allarmi")
def allarmi():
    history = alerts.read_history()
    return render_template("allarmi.html", history=history)


@app.route("/configurazione", methods=["GET", "POST"])
def configurazione():
    cfg = load_config()
    saved = False
    if request.method == "POST":
        th = cfg["thresholds"]
        for key in th:
            if key in request.form:
                th[key] = float(request.form[key])
        cfg["subsystems_required"] = [
            s.strip() for s in request.form.get("subsystems", "").split(",")
            if s.strip()]
        import os
        import yaml
        path = os.environ.get("TWG_CONFIG", os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "config.yaml"))
        with open(path, "w", encoding="utf-8") as fh:
            yaml.safe_dump(cfg, fh, allow_unicode=True, sort_keys=False)
        saved = True
    return render_template("configurazione.html", cfg=cfg, saved=saved)


@app.route("/api/stato")
def api_stato():
    with STATE["lock"]:
        return jsonify(STATE["data"])


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    refresh()
    return jsonify({"ok": True})


@app.route("/api/report", methods=["POST"])
def api_report():
    cfg = load_config()
    with STATE["lock"]:
        checks, data = list(STATE["checks"]), dict(STATE["data"])
    path = report.generate_pdf(cfg, checks, data)
    return jsonify({"ok": True, "path": path})


if __name__ == "__main__":
    cfg = load_config()
    refresh()
    t = threading.Thread(target=poller, args=(cfg.get("poll_seconds", 300),),
                         daemon=True)
    t.start()
    app.run(host="127.0.0.1", port=5000, debug=False)
