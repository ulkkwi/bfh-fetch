# test_generate_weekly_report.py
from generate_weekly_report import create_weekly_pdf

dummy_summaries = [
    {
        "title": "VI R 4/23 – Steuerliche Behandlung von Kryptowährungen",
        "published": "Thu, 04 Sep 2025 10:00:02 +0200",
        "link": "https://www.bundesfinanzhof.de/de/entscheidung/entscheidungen-online/detail/STRE202510171/",
        "leitsatz": "Einnahmen aus der Veräußerung von Kryptowährungen sind steuerpflichtig, wenn die Veräußerung innerhalb eines Jahres nach Anschaffung erfolgt.",
        "summary": "Der Bundesfinanzhof stellt klar, dass Kryptowährungen als Wirtschaftsgüter einzustufen sind. Gewinne aus kurzfristigem Handel sind damit steuerpflichtig. Eine Ausnahme gilt nur bei Haltefristen über einem Jahr."
    }
]

if __name__ == "__main__":
    create_weekly_pdf(dummy_summaries, "test_weekly_report.pdf", model="gpt-5-nano")
