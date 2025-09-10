import os
from datetime import datetime
from generate_weekly_report import create_weekly_pdf

def test_create_weekly_pdf():
    summaries = [
        {
            "title": "VI R 4/23 – Einkommensteuer: Dienstwagenbesteuerung",
            "published": "Thu, 04 Sep 2025 10:00:02 +0200",
            "link": "https://www.bundesfinanzhof.de/de/entscheidung/entscheidungen-online/detail/STRE202510171/",
            "leitsatz": "Bei der Überlassung eines Dienstwagens ...",
            "summary": "Der BFH entschied, dass die private Nutzung eines Dienstwagens ..."
        }
    ]

    outdir = "tests"
    os.makedirs(outdir, exist_ok=True)

    filename = os.path.join(outdir, f"test_weekly_report_{datetime.now().strftime('%Y%m%d')}.pdf")
    create_weekly_pdf(summaries, filename, model="gpt-5-nano")

    assert os.path.exists(filename), "PDF wurde nicht erstellt!"
    assert os.path.getsize(filename) > 1000, "PDF ist zu klein, vermutlich leer."
    print(f"✅ Test-PDF erstellt: {filename}")