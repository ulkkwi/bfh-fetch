import os
import re
import requests
import feedparser
import locale
from datetime import datetime, date
from bs4 import BeautifulSoup
from PyPDF2 import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_JUSTIFY
from openai import OpenAI

# -------------------
# Konfiguration
# -------------------
client = OpenAI()
DEFAULT_MODEL = os.getenv("MODEL", "gpt-5-nano")
TEST_MODE = os.getenv("TEST_MODE") == "1"

# deutsche Locale für Datumsformat
try:
    locale.setlocale(locale.LC_TIME, "de_DE.UTF-8")
except locale.Error:
    # Fallback, falls Locale auf System nicht vorhanden
    pass

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

def download_pdf(url: str, folder="downloads"):
    os.makedirs(folder, exist_ok=True)
    filename = os.path.join(folder, url.split("/")[-1] + ".pdf")
    r = requests.get(url)
    with open(filename, "wb") as f:
        f.write(r.content)
    return filename

def extract_text_from_pdf(path: str) -> str:
    text = ""
    with open(path, "rb") as f:
        reader = PdfReader(f)
        for page in reader.pages:
            text += page.extract_text() or ""
    print(f"📄 {os.path.basename(path)} – Länge extrahierter Text: {len(text)} Zeichen")
    return text

# -------------------
# OpenAI Anbindung
# -------------------
def call_openai(model: str, prompt: str, max_tokens: int = 800) -> str:
    try:
        print(f"📝 Prompt-Länge: {len(prompt)} Zeichen")
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Fasse den folgenden Abschnitt sehr kurz in 2–3 Sätzen zusammen. "
                        "Vermeide Stichpunkte, Überschriften und die Wörter 'Zusammenfassung' oder 'Kurzfassung'. "
                        "Schreibe klar und verständlich auf Deutsch."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            max_completion_tokens=max_tokens,
        )
        if (
            response.choices
            and response.choices[0].message
            and response.choices[0].message.content
        ):
            content = response.choices[0].message.content.strip()
            print(f"🔎 Preview ({model}): {content[:200]}...")
            print(f"📏 Antwort-Länge: {len(content)} Zeichen")
            return content
        else:
            print(f"⚠️ Modell {model} hat keine verwertbare Antwort geliefert.")
            print("🔎 API-Rohantwort:", response)
    except Exception as e:
        print(f"⚠️ Fehler mit Modell {model}: {e}")
    return ""

def summarize_text(text: str) -> str:
    chunk_size = 1000
    chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
    summaries = []

    for idx, chunk in enumerate(chunks, 1):
        summary = call_openai(DEFAULT_MODEL, chunk)
        if not summary:
            print("⚠️ Nano liefert nichts – wechsle zu gpt-5-mini")
            summary = call_openai("gpt-5-mini", chunk)
        summaries.append(summary or "⚠️ Keine Antwort erhalten")
        print(f"✅ Chunk {idx}: {len(summaries[-1])} Zeichen Summary")

    # Finale Gesamtsumme aus allen Chunk-Summaries
    combined = "\n".join(summaries)
    final = call_openai(
        DEFAULT_MODEL,
        f"Fasse die folgenden Teilsummen in höchstens 2 Absätzen narrativ zusammen:\n{combined}",
        500,
    )
    return final or combined

# -------------------
# Kosten
# -------------------
def estimate_cost(num_decisions: int, model: str) -> float:
    if model not in PRICES:
        return 0.0
    input_tokens = num_decisions * 30000
    output_tokens = num_decisions * 1000
    price_in = PRICES[model]["input"] / 1_000_000
    price_out = PRICES[model]["output"] / 1_000_000
    return round(input_tokens * price_in + output_tokens * price_out, 4)

# -------------------
# PDF Bericht
# -------------------
def create_weekly_pdf(summaries, filename):
    doc = SimpleDocTemplate(filename, pagesize=A4)
    styles = getSampleStyleSheet()

    # eigener deutscher Absatzstil
    styles.add(ParagraphStyle(
        name="German",
        parent=styles["Normal"],
        alignment=TA_JUSTIFY,
        leading=14,
        spaceAfter=10,
    ))

    story = []
    today = date.today()
    year, week, _ = datetime.now().isocalendar()

    # Titelseite
    story.append(Spacer(1, 5*cm))
    story.append(Paragraph("<para align='center'><b>Bundesfinanzhof</b></para>", styles["Title"]))
    story.append(Spacer(1, 1*cm))
    story.append(Paragraph("<para align='center'>Wochenbericht zu aktuellen Entscheidungen</para>", styles["Title"]))
    story.append(Spacer(1, 3*cm))

    data = [
        ["Kalenderwoche:", f"{week} / {year}"],
        ["Erstellt am:", today.strftime("%d. %B %Y")],
    ]
    table = Table(data, colWidths=[5*cm, 10*cm])
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("FONT", (0, 0), (-1, -1), "Helvetica", 12),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
    ]))
    story.append(table)
    story.append(PageBreak())

    # Inhalt
    story.append(Paragraph("<b>Zusammenfassungen der Entscheidungen</b>", styles["Heading1"]))
    story.append(Spacer(1, 20))

    for entry in summaries:
        case_number = extract_case_number(entry['title'])
        story.append(Paragraph(f"<b>{case_number} – {entry['title']}</b>", styles["Heading2"]))
        story.append(Paragraph(f"Veröffentlicht: {entry['published']}", styles["Normal"]))
        story.append(Paragraph(f"Link: <a href='{entry['link']}'>{entry['link']}</a>", styles["Normal"]))
        story.append(Spacer(1, 10))
        story.append(Paragraph(entry["summary"], styles["German"]))
        story.append(Spacer(1, 20))

    # Hinweise
    story.append(PageBreak())
    story.append(Paragraph("<b>Technische Hinweise</b>", styles["Heading1"]))
    story.append(Spacer(1, 10))
    story.append(Paragraph(f"Zusammenfassungen automatisch erstellt mit Modell <b>{DEFAULT_MODEL}</b>.", styles["Normal"]))
    est_cost = estimate_cost(len(summaries), DEFAULT_MODEL)
    story.append(Paragraph(f"Geschätzte API-Kosten: ca. {est_cost} USD/Woche.", styles["Normal"]))
    story.append(Paragraph("Quelle: RSS-Feed des Bundesfinanzhofs.", styles["Normal"]))

    doc.build(story)
    print(f"📄 Wochen-PDF erstellt: {filename}")

# -------------------
# Hauptlogik
# -------------------
def main():
    FEED_URL = "https://www.bundesfinanzhof.de/de/precedent.rss"
    feed = feedparser.parse(FEED_URL)

    summaries = []
    entries = feed.entries[:1] if TEST_MODE else feed.entries
    if TEST_MODE:
        print("🧪 Testmodus aktiv: nur 1 Entscheidung wird verarbeitet")

    for entry in entries:
        pdf_url = None
        try:
            html = requests.get(entry.link).text
            soup = BeautifulSoup(html, "html.parser")
            link_tag = soup.find("a", href=re.compile(r"/pdf/"))
            if link_tag:
                pdf_url = "https://www.bundesfinanzhof.de" + link_tag["href"]
        except Exception as e:
            print("⚠️ Konnte PDF-Link nicht ermitteln:", e)

        if not pdf_url:
            print(f"⚠️ Keine PDF-URL für {entry.title}")
            continue

        pdf_path = download_pdf(pdf_url)
        text = extract_text_from_pdf(pdf_path)
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
