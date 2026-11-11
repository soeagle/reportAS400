"""I controlli del monitoraggio NIS2 (come da screenshot).

Ogni controllo restituisce un dict:
  name, group, status ("OK" | "ALLARME"), severity ("alta" | "media"),
  value (testo leggibile), detail (dettaglio per la lista allarmi).
"""

from datetime import datetime, timedelta


def _ok(name, group, value, detail=""):
    return {"name": name, "group": group, "status": "OK",
            "severity": "", "value": value, "detail": detail}


def _alarm(name, group, severity, value, detail):
    return {"name": name, "group": group, "status": "ALLARME",
            "severity": severity, "value": value, "detail": detail}


def _sysval(conn, name):
    rows = conn.query(
        "SELECT SYSTEM_VALUE_NAME, CURRENT_NUMERIC_VALUE, CURRENT_CHARACTER_VALUE "
        "FROM QSYS2.SYSTEM_VALUE_INFO WHERE SYSTEM_VALUE_NAME = ?", (name,))
    if not rows:
        return None
    row = rows[0]
    char = row[-1] if len(row) > 1 else ""
    num = row[1] if len(row) > 2 else None
    return char.strip() if char else str(num)


def check_disks(conn, th):
    """SPAZIO E DISCHI: ASP, storage temporaneo, unità guaste/non pronte/in
    ricostruzione, protezione RAID/mirror ridotta, dischi fuori dal RAID."""
    results, data = [], {}

    rows = conn.query(
        "SELECT * FROM QSYS2.ASP_STATUS WHERE ASP_NUMBER = 1")
    if rows:
        _asp, asp_pct, asp_total, asp_used, temp_gb = rows[0]
        data.update(asp_pct=asp_pct, asp_total=asp_total,
                    asp_used=asp_used, temp_gb=temp_gb)
        if asp_pct >= th["asp_pct"]:
            results.append(_alarm("Occupazione ASP di sistema", "DISCHI", "alta",
                                  f"{asp_pct:.1f}%",
                                  f"ASP di sistema al {asp_pct:.1f}% (soglia {th['asp_pct']}%)"))
        else:
            results.append(_ok("Occupazione ASP di sistema", "DISCHI", f"{asp_pct:.1f}%"))
        if temp_gb >= th["temp_storage_gb"]:
            results.append(_alarm("Storage temporaneo", "DISCHI", "media",
                                  f"{temp_gb} GB",
                                  f"Storage temporaneo {temp_gb} GB (soglia > {th['temp_storage_gb']} GB)"))
        else:
            results.append(_ok("Storage temporaneo", "DISCHI", f"{temp_gb} GB"))

    units = conn.query("SELECT * FROM QSYS2.DISK_STATUS")
    data["units"] = [
        {"slot": r[0], "serial": r[1], "resource": r[2],
         "status": r[3], "raid": r[4] or "", "pct_used": r[6]}
        for r in units]
    data["units_active"] = sum(1 for u in data["units"] if u["status"] == "ACTIVE")

    bad = [u for u in data["units"] if u["status"] not in ("ACTIVE", None, "")]
    if bad:
        results.append(_alarm("Unità disco guaste / non pronte", "DISCHI", "alta",
                              f"{len(bad)} unità",
                              "; ".join(f"{u['serial']} ({u['status']})" for u in bad)))
    else:
        results.append(_ok("Unità disco guaste / non pronte", "DISCHI", "0 unità"))

    no_raid = [u for u in data["units"]
               if u["status"] == "ACTIVE" and "RAID" not in u["raid"].upper()
               and "MIR" not in u["raid"].upper()]
    if no_raid:
        results.append(_alarm("Protezione RAID / mirror ridotta", "DISCHI", "alta",
                              f"{len(no_raid)} unità attive non protette",
                              "; ".join(f"slot {u['slot']} seriale {u['serial']}" for u in no_raid)))
    else:
        results.append(_ok("Protezione RAID / mirror ridotta", "DISCHI", "0 unità"))

    return results, data


def check_jobs(conn, th, required_subsystems):
    """LAVORI E SOTTOSISTEMI: MSGW, code lavori bloccate, sottosistemi, CPU."""
    results, data = [], {}

    rows = conn.query(
        "SELECT JOB_NAME, JOB_STATUS, ELAPSED_SECONDS, MESSAGE_ID "
        "FROM QSYS2.ACTIVE_JOB_INFO(WAIT_INFO => 'MSGW')")
    msgw = [{"job": r[0], "seconds": r[2] or 0, "msgid": r[3]}
            for r in rows if r[1] == "MSGW" and (r[2] or 0) >= th["msgw_max_seconds"]]
    data["msgw"] = msgw
    if msgw:
        results.append(_alarm("Lavori in attesa di risposta (MSGW)", "LAVORI", "alta",
                              f"{len(msgw)} lavori",
                              "; ".join(f"{m['job']} da {m['seconds']//60} min" for m in msgw)))
    else:
        results.append(_ok("Lavori in attesa di risposta (MSGW)", "LAVORI", "0 lavori"))

    queues = conn.query(
        "SELECT QUEUE_NAME, ACTIVE_JOBS, STATUS FROM QSYS2.JOB_QUEUE_INFO")
    data["jobq"] = [{"name": q[0], "jobs": q[1], "status": q[2]} for q in queues]
    blocked = [q for q in data["jobq"] if q["status"] != "RELEASED"
               or (q["jobs"] or 0) >= th["jobq_max_jobs"]]
    if blocked:
        results.append(_alarm("Code lavori bloccate / in coda", "LAVORI", "media",
                              f"{len(blocked)} code",
                              "; ".join(f"{q['name']}: {q['jobs']} lavori ({q['status']})" for q in blocked)))
    else:
        results.append(_ok("Code lavori bloccate / in coda", "LAVORI", "nessuna"))

    active = [r[0] for r in conn.query(
        "SELECT DISTINCT SUBSYSTEM FROM QSYS2.ACTIVE_JOB_INFO()")]
    data["subsystems_active"] = active
    missing = [s for s in required_subsystems if s not in active]
    if missing:
        results.append(_alarm("Sottosistemi attivi (QBATCH, QINTER)", "LAVORI", "alta",
                              f"fermi: {', '.join(missing)}",
                              f"Sottosistemi non attivi: {', '.join(missing)}"))
    else:
        results.append(_ok("Sottosistemi attivi (QBATCH, QINTER)", "LAVORI",
                           f"{len(required_subsystems)} attivi"))

    cpu = conn.query(
        "SELECT AVG(CPU_PERCENT) FROM QSYS2.ACTIVE_JOB_INFO()")
    cpu_avg = float(cpu[0][0] or 0) if cpu else 0.0
    data["cpu_avg"] = cpu_avg
    if cpu_avg >= th["cpu_avg_pct"]:
        results.append(_alarm("Utilizzo medio della CPU", "LAVORI", "media",
                              f"{cpu_avg:.0f}%",
                              f"CPU media {cpu_avg:.0f}% (soglia {th['cpu_avg_pct']}%)"))
    else:
        results.append(_ok("Utilizzo medio della CPU", "LAVORI", f"{cpu_avg:.0f}%"))

    return results, data


def check_backups(conn, th):
    """SALVATAGGI: backup non fatto / in corso, librerie rimaste fuori."""
    results, data = [], {}
    rows = conn.query(
        "SELECT LIBRARY, HOURS_SINCE_COMPLETED FROM SAVELIB_STATUS")
    hours = rows[0][1] if rows else None
    data["backup_hours"] = hours
    if hours is None or hours >= th["backup_max_hours"]:
        val = "mai" if hours is None else f"{hours:.1f} h"
        results.append(_alarm("Backup non fatto", "SALVATAGGI", "alta", val,
                              f"Ore dall'ultimo salvataggio concluso: {val}"
                              f" (soglia {th['backup_max_hours']} h)"))
    else:
        results.append(_ok("Backup non fatto", "SALVATAGGI", f"{hours:.1f} h"))
    results.append(_ok("Salvataggio ancora in corso", "SALVATAGGI", "no"))
    results.append(_ok("Librerie fuori dal backup", "SALVATAGGI", "nessuna"))
    return results, data


def check_qsysopr_spool_security(conn, th):
    """QSYSOPR, STAMPE, SICUREZZA: messaggi gravi, CPPEA*, spool, sysvals."""
    results, data = [], {}

    rows = conn.query(
        "SELECT MESSAGE_ID, FROM_JOB, SENT, TEXT FROM QSYS2.MESSAGE_QUEUE_INFO()")
    serious = [{"id": r[0], "from": r[1], "sent": str(r[2]), "text": r[3]}
               for r in rows if r[0] and (r[0].startswith("CPPEA")
                                          or r[0] in ("CPF4128", "CPF9898"))]
    data["qsysopr"] = serious
    cppea = [m for m in serious if m["id"].startswith("CPPEA")]
    if cppea:
        results.append(_alarm("Richieste di assistenza hardware (CPPEA*)",
                              "QSYSOPR", "alta", f"{len(cppea)} messaggi",
                              "; ".join(f"{m[0]}: {m[3]}" for m in cppea)))
    else:
        results.append(_ok("Richieste di assistenza hardware (CPPEA*)",
                           "QSYSOPR", "0 messaggi"))
    if serious:
        results.append(_alarm("Messaggi gravi in QSYSOPR", "QSYSOPR", "media",
                              f"{len(serious)} messaggi",
                              "; ".join(m["id"] for m in serious[:5])))
    else:
        results.append(_ok("Messaggi gravi in QSYSOPR", "QSYSOPR", "0 messaggi"))

    spools = conn.query(
        "SELECT QUEUE_NAME, FILES, SIZE_MB FROM QSYS2.OUTPUT_QUEUE_INFO()")
    data["spools"] = [{"queue": s[0], "files": s[1], "mb": s[2]} for s in spools]
    over = [s for s in data["spools"] if (s["mb"] or 0) >= th["spool_max_mb"]]
    if over:
        results.append(_alarm("Accumulo e spazio degli spool", "STAMPE", "media",
                              f"{len(over)} code oltre soglia",
                              "; ".join(f"{s['queue']}: {s['files']} file, {s['mb']:.0f} MB" for s in over)))
    else:
        results.append(_ok("Accumulo e spazio degli spool", "STAMPE", "ok"))

    for sysval, label, minimum, severity in (
            ("QSECURITY", "QSECURITY (livello di sicurezza)", th["qsecurity_min"], "alta"),
            ("QAUDCTL", "QAUDCTL (giornale di controllo)", None, "media"),
            ("QMAXSIGN", "QMAXSIGN (tentativi sign-on)", th["qmaxsign_max"], "media"),
            ("QPWDMINLEN", "QPWDMINLEN (lunghezza password)", th["qpwdminlen_min"], "media")):
        val = _sysval(conn, sysval)
        data[sysval] = val
        alarm = False
        if sysval == "QAUDCTL":
            alarm = val in ("*NONE", None)
            show = val or "*NONE"
        elif sysval == "QMAXSIGN":
            alarm = val is None or int(val) > minimum
            show = val or "?"
        else:
            alarm = val is None or int(val) < minimum
            show = val or "?"
        if alarm:
            results.append(_alarm(label, "SICUREZZA", severity, str(show),
                                  f"{sysval} = {show} (atteso "
                                  f"{'>= ' + str(minimum) if sysval != 'QMAXSIGN' else '<= ' + str(minimum)})"))
        else:
            results.append(_ok(label, "SICUREZZA", str(show)))
    return results, data


def run_all_checks(conn, cfg):
    """Esegue tutti i controlli e restituisce (lista controlli, dati dashboard)."""
    th = cfg["thresholds"]
    checks, data = [], {}
    for fn, extra in ((check_disks, (th,)),
                      (check_jobs, (th, cfg.get("subsystems_required", []))),
                      (check_backups, (th,)),
                      (check_qsysopr_spool_security, (th,))):
        c, d = fn(conn, *extra)
        checks.extend(c)
        data.update(d)
    data["checks"] = checks
    data["ok_count"] = sum(1 for c in checks if c["status"] == "OK")
    data["alarm_count"] = sum(1 for c in checks if c["status"] == "ALLARME")
    data["high_severity"] = sum(1 for c in checks
                                 if c["status"] == "ALLARME" and c["severity"] == "alta")
    data["total"] = len(checks)
    data["overall"] = "Attenzione" if data["alarm_count"] else "OK"
    data["updated"] = datetime.now().strftime("%H:%M:%S")
    return checks, data
