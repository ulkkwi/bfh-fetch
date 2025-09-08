import os
import re
import requests
import feedparser
from datetime import datetime, date
from bs4 import BeautifulSoup   # --- NEU ---
from PyPDF2 import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.units import cm
from openai import OpenAI
import locale

# -------------------
# Konfiguration
# -------------------
client = OpenAI()
DEFAULT_MODEL = os.getenv("MODEL", "gpt-5-nano")

PRICES = {
    "gpt-5-nano": {"input": 0.05, "output": 0.40},
    "gpt-5-mini": {"input": 0.25, "output": 2.00},
    "gpt-5": {"input": 1.25, "output": 10.00},
}

try:
    locale.setlocale(locale.LC_TIME, "de_DE.UTF-8")
except locale.Error:
    pass


# -------------------
# Hilfsfunktionen
# -------------------
def extract_case_number(title: str) -> str:
    match = re.search(r"[A-Z]{1,3}\s?[A-Z]?\s?\d+/\d{2}", title)
    return match.group(0) if match else "Unbekannt"


def download_pdf(url: str, folder="downloads"):
    os.makedirs(folder, exist_ok=True)
    filename = os.path.join(folder, url.split("/")[-1] + ".pdf")
    r = requests.get(url)
    with open(filename, "wb") as f:
        f.write(r.content)
    return filename


# --- NEU: Echten PDF-Link von der Detailseite holen ---
def get_pdf_link(detail_url: str) -> str:
    """Holt den echten PDF-Link von der Detailseite"""
    r = requests.get(detail_url)
    soup = BeautifulSoup(r.text, "html.parser")
    link_tag = soup.find("a", href=lambda x: x and "detail/pdf" in x)
    if link_tag:
        return "https://www.bundesfinanzhof.de" + link_tag["href"]
    raise ValueError(f"Kein PDF-Link gefunden auf {detail_url}")


def extract_text_from_pdf(path: str) -> str:
    text = ""
    with open(path, "rb") as f:
        reader = PdfReader(f)
        for page in reader.pages:
            text += page.extract_text() or ""
    return text


def clean_text(text: str) -> str:
    text = re.sub(r"(\w+)-\s+(\w+)", r"\1\2", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_leitsaetze(text: str) -> str:
    if "Leitsätze" not in text:
        return ""
    leitsatz = text.split("Leitsätze", 1)[1]
    if "Tenor" in leitsatz:
        leitsatz = leitsatz.split("Tenor", 1)[0]
    return clean_text(leitsatz.strip())


def format_date(date_str: str) -> str:
    try:
        dt = datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %z")
        return dt.strftime("%d.%m.%Y")
    except Exception:
        return date_str


def summarize_text(text: str) -> str:
    text = clean_text(text)
    response = client.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "Du bist ein juristischer Assistent. "
                    "Fasse die folgende BFH-Entscheidung in **höchstens 5 Sätzen** "
                    "verständlich und narrativ zusammen. "
                    "Vermeide Gesetzeszitate, Fachchinesisch und Wiederholungen."
                ),
            },
            {"role": "user", "content": text},
        ],
        max_completion_tokens=500,
    )
    return response.choices[0].message.content.strip()


def estimate_cost(num_decisions: int, model: str) -> float:
    if model not in PRICES:
        return 0.0
    input_tokens = num_decisions * 30000
    output_tokens = num_decisions * 500
    price_in = PRICES[model]["input"] / 1_000_000
    price_out = PRICES[model]["output"] / 1_000_000
    return round(input_tokens * price_in + output_tokens * price_out, 4)


def create_weekly_pdf(summaries, filename):
    doc = SimpleDocTemplate(filename, pagesize=A4)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Block", parent=styles["Normal"], alignment=4))

    story = []
    today = date.today()
    year, week, _ = datetime.now().isocalendar()

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

    story.append(Paragraph("<b>Zusammenfassungen der Entscheidungen</b>", styles["Heading1"]))
    story.append(Spacer(1, 20))

    for entry in summaries:
        case_number = extract_case_number(entry['title'])
        story.append(Paragraph(f"<b>{case_number} – {entry['title']}</b>", styles["Heading2"]))
        story.append(Paragraph(f"Veröffentlicht: {entry['published']}", styles["Normal"]))
        story.append(Paragraph(f"Link: <a href='{entry['link']}'>{entry['link']}</a>", styles["Normal"]))
        story.append(Spacer(1, 10))

        if entry.get("leitsaetze"):
            story.append(Paragraph("<b>Leitsätze:</b>", styles["Heading3"]))
            story.append(Paragraph(entry["leitsaetze"], styles["Block"]))
            story.append(Spacer(1, 10))

        story.append(Paragraph(entry["summary"], styles["Block"]))
        story.append(Spacer(1, 20))

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

    # --- NEU: TEST_MODE ---
    test_mode = os.getenv("TEST_MODE", "0") == "1"
    if test_mode:
        print("🧪 Testmodus aktiv: nur 1 Entscheidung wird verarbeitet")
        entries = feed.entries[:1]
    else:
        entries = feed.entries

    summaries = []
    for entry in entries:
        pdf_link = get_pdf_link(entry.link)  # --- NEU ---
        pdf_path = download_pdf(pdf_link)
        raw_text = extract_text_from_pdf(pdf_path)
        text = clean_text(raw_text)
        summary = summarize_text(text)
        leitsaetze = extract_leitsaetze(raw_text)

        summaries.append({
            "title": entry.title,
            "published": format_date(entry.published),
            "link": entry.link,
            "summary": summary,
            "leitsaetze": leitsaetze,
        })

    os.makedirs("weekly_reports", exist_ok=True)
    filename = f"weekly_reports/BFH_Entscheidungen_KW{datetime.now().isocalendar()[1]}_{datetime.now().year}.pdf"
    create_weekly_pdf(summaries, filename)


if __name__ == "__main__":
    main()
