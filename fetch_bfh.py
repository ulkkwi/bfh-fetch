import os
import re
import requests
import feedparser
from datetime import datetime, date
from bs4 import BeautifulSoup
from PyPDF2 import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.units import cm
from openai import OpenAI

# -------------------
# Konfiguration
# -------------------
client = OpenAI()
DEFAULT_MODEL = os.getenv("MODEL", "gpt-5-nano")
TEST_MODE = os.getenv("TEST_MODE", "0") == "1"  # Flag aus Umgebungsvariable

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
    match = re.search(r"[A-Z]{1,3}\s?[A-Z]?\s?\d+/\d{2}", title)
    return match.group(0) if match else "Unbekannt"

def sanitize_filename(name: str) -> str:
    return "".join(c if c.isalnum() or c in ("_", "-", ".") else "_" for c in name)

def find_pdf_link(detail_url: str) -> str | None:
    r = requests.get(detail_url)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/detail/pdf/" in href:
            if not href.startswith("http"):
                href = "https://www.bundesfinanzhof.de" + href
            return href
    return None

def download_pdf(pdf_link: str, aktenzeichen: str, folder="downloads"):
    os.makedirs(folder, exist_ok=True)
    response = requests.get(pdf_link)
    response.raise_for_status()

    clean_az = sanitize_filename(aktenzeichen)
    basename = f"{clean_az}_{datetime.now().strftime('%Y%m%d')}.pdf"
    filename = os.path.join(folder, basename)

    with open(filename, "wb") as f:
        f.write(response.content)
    return filename

def extract_text_from_pdf(path: str) -> str:
    text = ""
    with open(path, "rb") as f:
        reader = PdfReader(f)
        for page in reader.pages:
            text += page.extract_text() or ""
    return text

def summarize_text(text: str) -> str:
    # ---- Split in kleine Chunks (~2000 Zeichen) ----
    max_chunk_size = 2000
    chunks = [text[i:i+max_chunk_size] for i in range(0, len(text), max_chunk_size)]

    partial_summaries = []

    # ---- Abschnitte einzeln zusammenfassen ----
    for idx, chunk in enumerate(chunks, 1):
        try:
            response = client.chat.completions.create(
                model=DEFAULT_MODEL,
                messages=[
                    {"role": "system", "content": "Fasse diesen Abschnitt einer BFH-Entscheidung präzise auf Deutsch zusammen."},
                    {"role": "user", "content": chunk},
                ],
                max_completion_tokens=150,
            )
            summary = response.choices[0].message.content.strip()
            partial_summaries.append(summary)
        except Exception as e:
            print(f"⚠️ Fehler bei Chunk {idx}: {e}")

    if not partial_summaries:
        return "⚠️ Keine Zusammenfassung möglich."

    # ---- Gesamtsynthese ----
    combined_text = "\n".join(partial_summaries)
    try:
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": "Du bist ein juristischer Assistent. "
                                              "Fasse die gesamte BFH-Entscheidung narrativ in 2 Absätzen zusammen. "
                                              "Vermeide Fußnoten und Gesetzeszitate."},
                {"role": "user", "content": combined_text},
            ],
            max_completion_tokens=300,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"⚠️ Fehler bei Gesamtsynthese: {e}")
        return "\n".join(partial_summaries)

def estimate_cost(num_decisions: int, model: str) -> float:
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
        heading = entry['title'] if case_number in entry['title'] else f"{case_number} – {entry['title']}"

        story.append(Paragraph(f"<b>{heading}</b>", styles["Heading2"]))
        story.append(Paragraph(f"Veröffentlicht: {entry['published']}", styles["Normal"]))
        story.append(Paragraph(f"Link: <a href='{entry['link']}'>{entry['link']}</a>", styles["Normal"]))
        story.append(Spacer(1, 10))
        story.append(Paragraph(entry["summary"], styles["Normal"]))
        story.append(Spacer(1, 20))

    # ---- Technischer Hinweis ----
    story.append(PageBreak())
    story.append(Paragraph("<b>Technische Hinweise</b>", styles["Heading1"]))
    story.append(Spacer(1, 10))
    story.append(Paragraph(f"Die Zusammenfassungen wurden automatisch mit dem Modell <b>{DEFAULT_MODEL}</b> erstellt.", styles["Normal"]))
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

    if not feed.entries:
        print("⚠️ Keine neuen Entscheidungen im RSS-Feed gefunden.")
        return

    entries = feed.entries
    if TEST_MODE:
        entries = entries[:1]
        print("🧪 Testmodus aktiv: nur 1 Entscheidung wird verarbeitet")

    summaries = []
    for entry in entries:
        case_number = extract_case_number(entry.title)
        pdf_link = find_pdf_link(entry.link)
        if not pdf_link:
            print(f"⚠️ Kein PDF-Link gefunden für {entry.link}")
            continue

        pdf_path = download_pdf(pdf_link, case_number)
        text = extract_text_from_pdf(pdf_path)
        print(f"📄 {os.path.basename(pdf_path)} – Länge extrahierter Text: {len(text)} Zeichen")

        summary = summarize_text(text)

        summaries.append({
            "title": entry.title,
            "published": entry.published,
            "link": entry.link,
            "summary": summary,
        })

    os.makedirs("weekly_reports", exist_ok=True)
    filename = f"weekly_reports/BFH_Entscheidungen_KW{datetime.now().isocalendar()[1]}_{datetime.now().year}.pdf"
    create_weekly_pdf(summaries, filename)

if __name__ == "__main__":
    main()
