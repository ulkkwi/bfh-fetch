import os
import re
import requests
import feedparser
from datetime import datetime, date
from PyPDF2 import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.units import cm
from openai import OpenAI
from bs4 import BeautifulSoup
import locale

# -------------------
# Konfiguration
# -------------------
client = OpenAI()
DEFAULT_MODEL = os.getenv("MODEL", "gpt-5-nano")  # Modell aus Umgebungsvariable oder Default

# Preise pro 1M Tokens (USD) – Stand 2025
PRICES = {
    "gpt-5-nano": {"input": 0.05, "output": 0.40},
    "gpt-5-mini": {"input": 0.25, "output": 2.00},
    "gpt-5": {"input": 1.25, "output": 10.00},
}

# -------------------
# Hilfsfunktionen
# -------------------
def extract_case_number(title: str) -> str:
    """Extrahiert das Aktenzeichen (z. B. VI R 4/23) aus dem Titel"""
    match = re.search(r"[A-Z]{1,3}\s?[A-Z]?\s?\d+/\d{2}", title)
    return match.group(0) if match else "Unbekannt"

# BFH PDFs sauber benennen (ignoriere ?type=...)
def download_pdf(url: str, folder="downloads"):
    os.makedirs(folder, exist_ok=True)

    basename = url.split("/")[-1].split("?")[0]  # Query-Teil abschneiden
    if not basename.lower().endswith(".pdf"):
        basename = f"{basename}.pdf"

    filename = os.path.join(folder, basename)

    r = requests.get(url)
    r.raise_for_status()
    with open(filename, "wb") as f:
        f.write(r.content)

    return filename

def extract_text_from_pdf(path: str) -> str:
    text = ""
    with open(path, "rb") as f:
        reader = PdfReader(f)
        for page in reader.pages:
            text += page.extract_text() or ""
    return text

def extract_leitsatz(text: str) -> str:
    """Schneidet die Leitsätze bis vor 'Tenor' heraus"""
    m = re.search(r"Leitsätze:(.*?)(?=Tenor)", text, re.S | re.I)
    if m:
        return m.group(1).strip()
    return ""

# Fallback-Logik für Modelle
def summarize_text(text: str) -> str:
    models = ["gpt-5-nano", "gpt-5-mini", "gpt-5"]
    for model in models:
        try:
            print(f"➡️ Versuche Modell: {model}")
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Du bist ein juristischer Assistent. "
                            "Fasse die BFH-Entscheidung in EINEM kurzen Absatz zusammen. "
                            "Maximal 5 Sätze. "
                            "Vermeide Fußnoten, Aktenzeichen und Zitate. "
                            "Erkläre den Kern der Entscheidung so, dass Steuerberater:innen ihn in 30 Sekunden erfassen können."
                        ),
                    },
                    {"role": "user", "content": text},
                ],
                max_completion_tokens=500,
            )
            content = response.choices[0].message.content.strip()
            if content:
                return content
            else:
                print(f"⚠️ Modell {model} hat nichts geliefert, versuche nächstes...")
        except Exception as e:
            print(f"⚠️ Fehler mit Modell {model}: {e}")
    return "⚠️ Keine Antwort vom Modell erhalten."

def estimate_cost(num_decisions: int, model: str) -> float:
    """Schätzt die Kosten pro Woche (USD)"""
    if model not in PRICES:
        return 0.0
    input_tokens = num_decisions * 30000
    output_tokens = num_decisions * 500
    price_in = PRICES[model]["input"] / 1_000_000
    price_out = PRICES[model]["output"] / 1_000_000
    cost = input_tokens * price_in + output_tokens * price_out
    return round(cost, 4)

def create_weekly_pdf(summaries, filename):
    doc = SimpleDocTemplate(filename, pagesize=A4)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Justify", parent=styles["Normal"], alignment=4))  

    story = []

    today = date.today()
    year, week, _ = datetime.now().isocalendar()

    # ---- Titelseite ----
    story.append(Spacer(1, 5*cm))
    story.append(Paragraph("<para align='center'><b>Bundesfinanzhof</b></para>", styles["Title"]))
    story.append(Spacer(1, 1*cm))
    story.append(Paragraph("<para align='center'>Wochenbericht zu aktuellen Entscheidungen</para>", styles["Title"]))
    story.append(Spacer(1, 3*cm))

    data = [
        ["Kalenderwoche:", f"{week} / {year}"],
        ["Erstellt am:", today.strftime("%d.%m.%Y")],
    ]
    table = Table(data, colWidths=[5*cm, 10*cm])
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("FONT", (0, 0), (-1, -1), "Helvetica", 12),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
    ]))
    story.append(table)
    story.append(PageBreak())

    # ---- Inhalt ----
    story.append(Paragraph("<b>Zusammenfassungen der Entscheidungen</b>", styles["Heading1"]))
    story.append(Spacer(1, 20))

    for entry in summaries:
        case_number = extract_case_number(entry['title'])
        clean_title = entry['title'].replace(case_number, "").strip()  # kein doppeltes Aktenzeichen
        story.append(Paragraph(f"<b>{case_number} – {clean_title}</b>", styles["Heading2"]))

        try:
            locale.setlocale(locale.LC_TIME, "de_DE.utf8")
        except locale.Error:
            locale.setlocale(locale.LC_TIME, "C")

        pub_date = datetime.strptime(entry['published'], "%a, %d %b %Y %H:%M:%S %z")
        pub_date_str = pub_date.strftime("%d.%m.%Y, %H:%M Uhr")
        story.append(Paragraph(f"Veröffentlicht: {pub_date_str}", styles["Normal"]))

        story.append(Paragraph(f"Link: <a href='{entry['link']}'>{entry['link']}</a>", styles["Normal"]))
        story.append(Spacer(1, 10))

        if entry.get("leitsatz"):
            story.append(Paragraph("<b>Leitsätze:</b>", styles["Normal"]))
            story.append(Paragraph(entry["leitsatz"], styles["Justify"]))
            story.append(Spacer(1, 10))

        if entry.get("summary"):
            story.append(Paragraph("<b>Zusammenfassung:</b>", styles["Normal"]))
            story.append(Paragraph(entry["summary"], styles["Justify"]))
            story.append(Spacer(1, 20))

    # ---- Technischer Hinweis ----
    story.append(PageBreak())
    story.append(Paragraph("<b>Technische Hinweise</b>", styles["Heading1"]))
    story.append(Spacer(1, 10))
    story.append(Paragraph(f"Die Zusammenfassungen wurden automatisch mit dem Modell <b>{DEFAULT_MODEL}</b> erstellt (Fallback auf Mini/GPT-5 möglich).", styles["Normal"]))
    est_cost = estimate_cost(len(summaries), DEFAULT_MODEL)
    story.append(Spacer(1, 10))
    story.append(Paragraph(f"Geschätzte API-Kosten für diese Woche: ca. {est_cost} USD.", styles["Normal"]))
    story.append(Spacer(1, 10))
    story.append(Paragraph("Quelle: RSS-Feed des Bundesfinanzhofs.", styles["Normal"]))

    doc.build(story)
    print(f"📄 Wochen-PDF erstellt: {filename}")

# -------------------
# Hauptlogik
# -------------------
def main():
    FEED_URL = "https://www.bundesfinanzhof.de/de/precedent.rss"
    feed = feedparser.parse(FEED_URL)

    # CHANGE: Testmodus aus GitHub Actions
    test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
    if test_mode:
        print("🧪 Testmodus aktiv: nur 1 Entscheidung wird verarbeitet")
        feed.entries = feed.entries[:1]

    summaries = []
    for entry in feed.entries:
        # HTML-Seite der Entscheidung abrufen
        html_page = requests.get(entry.link).text
        soup = BeautifulSoup(html_page, "html.parser")

        # PDF-Link mit ?type= suchen
        pdf_tag = soup.find("a", href=True, string="PDF")
        if pdf_tag:
            pdf_link = "https://www.bundesfinanzhof.de" + pdf_tag["href"]
        else:
            print(f"⚠️ Kein PDF-Link für {entry.link} gefunden, überspringe...")
            continue

        pdf_path = download_pdf(pdf_link)
        raw_text = extract_text_from_pdf(pdf_path)

        leitsatz = extract_leitsatz(raw_text)
        summary = summarize_text(raw_text)

        summaries.append({
            "title": entry.title,
            "published": entry.published,
            "link": entry.link,
            "leitsatz": leitsatz,
            "summary": summary,
        })

    os.makedirs("weekly_reports", exist_ok=True)
    filename = f"weekly_reports/BFH_Entscheidungen_KW{datetime.now().isocalendar()[1]}_{datetime.now().year}.pdf"
    create_weekly_pdf(summaries, filename)

if __name__ == "__main__":
    main()
