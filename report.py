"""Report PDF mensile per ogni sistema (tracciabilità / evidenze NIS2)."""

import os
from datetime import datetime

from fpdf import FPDF

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def generate_pdf(cfg, checks, data, out_dir=None):
    out_dir = out_dir or os.path.join(BASE_DIR, cfg.get("report", {}).get(
        "output_dir", "reports"))
    os.makedirs(out_dir, exist_ok=True)
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "TwgIBMiControl - Report mensile IBM i", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Generato il {datetime.now():%d/%m/%Y %H:%M} - "
                   f"Sistema: {cfg['as400']['system']}",
              new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, f"Sintesi: {data['ok_count']} OK, {data['alarm_count']} in allarme"
                   f" ({data['high_severity']} a severità alta) su {data['total']} controlli",
              new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 6, "Controlli:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    for c in checks:
        mark = "OK " if c["status"] == "OK" else "AL!"
        pdf.cell(12, 5, mark)
        pdf.cell(0, 5, f"{c['name']} ({c['group']}): {c['value']}",
                 new_x="LMARGIN", new_y="NEXT")
    path = os.path.join(out_dir, f"report_{datetime.now():%Y%m}.pdf")
    pdf.output(path)
    return path
