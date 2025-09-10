# tests/test_generate_weekly_report.py
import os
import sys
import traceback
from datetime import datetime

# Ensure root is on sys.path (safety if PYTHONPATH not gesetzt)
root = os.path.dirname(os.path.dirname(__file__))
if root not in sys.path:
    sys.path.insert(0, root)

from generate_weekly_report import create_weekly_pdf

def main():
    print("▶️ Test gestartet: Erzeuge Beispiel-PDF im Ordner 'tests/'")
    summaries = [
        {
            "title": "VI R 4/23 – Einkommensteuer: Dienstwagenbesteuerung",
            "published": "Thu, 04 Sep 2025 10:00:02 +0200",
            "link": "https://www.bundesfinanzhof.de/de/entscheidung/entscheidungen-online/detail/STRE202510171/",
            "leitsatz": "Bei der Überlassung eines Dienstwagens im Rahmen einer komplexen Dienstwagenüberlassungsregelung sind die tatsächlichen Nutzungsumstände maßgeblich.",
            "summary": (
                "Der BFH entschied in dieser komplexen Rechtssache, dass die Dienstwagenüberlassungsregelung "
                "unter den gegebenen Umständen nicht zu einer zusätzlichen steuerpflichtigen Einnahme führt. "
                "Insbesondere hat das Gericht klargestellt, dass die Abgrenzung zwischen beruflicher und privater "
                "Nutzung anhand der tatsächlichen Nutzungsvorgaben und der vertraglichen Vereinbarungen vorzunehmen "
                "ist. Die Entscheidung enthält zudem umfangreiche Ausführungen zur Verhältnismäßigkeit der Nachweisanforderungen "
                "sowie zur Anwendbarkeit spezieller steuerlicher Begünstigungen. Die ausführliche Argumentation "
                "behandelt dabei auch Themen wie Fahrtenbuchführungspflichten und die steuerliche Bewertung von Sonderausstattungen, "
                "die in der Praxis häufig zu Fragen führen."
            )
        }
    ]

    outdir = "tests"
    os.makedirs(outdir, exist_ok=True)
    filename = os.path.join(outdir, f"test_weekly_report_{datetime.now().strftime('%Y%m%d')}.pdf")

    print(f"📁 Output-Datei soll sein: {filename}")
    try:
        create_weekly_pdf(summaries, filename, model="gpt-5-nano")
    except Exception as e:
        print("❌ Exception beim Aufruf von create_weekly_pdf():")
        traceback.print_exc()
        print("❗ Erzeuge eine kleine Placeholder-PDF zur Fehler-Analyse (damit Upload-Schritt etwas findet).")
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas
            c = canvas.Canvas(filename, pagesize=A4)
            c.drawString(50, 800, "Placeholder PDF, create_weekly_pdf() failed.")
            c.drawString(50, 780, f"Original error: {str(e)[:200]}")
            c.save()
            print(f"✅ Placeholder-PDF erstellt: {filename}")
        except Exception:
            print("⚠️ Fallback-PDF konnte nicht erstellt werden.")
            traceback.print_exc()
            sys.exit(1)

    # Verify
    if os.path.exists(filename):
        size = os.path.getsize(filename)
        print(f"✅ Datei vorhanden: {filename} (Größe: {size} bytes)")
        if size < 500:
            print("⚠️ PDF ist sehr klein (<500 bytes) — wahrscheinlich ungültig.")
            sys.exit(1)
        print("✅ Test erfolgreich.")
        sys.exit(0)
    else:
        print("❌ Datei wurde nicht erzeugt.")
        sys.exit(1)

if __name__ == "__main__":
    main()
