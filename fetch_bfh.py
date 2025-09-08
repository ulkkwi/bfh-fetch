import os
import re
import requests
import feedparser
from datetime import datetime, date
from bs4 import BeautifulSoup
from PyPDF2 import PdfReader
from openai import OpenAI

from generate_weekly_report import create_weekly_pdf  # PDF-Generierung ausgelagert

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


def extract_leitsaetze(text: str) -> str:
    """Extrahiert die Leitsätze aus dem Urteil (falls vorhanden)"""
    leitsatz_block = ""
    match = re.search(r"Leits(ä|ae)tze(.*?)(Gründe|Tatbestand)", text, re.S | re.I)
    if match:
        leitsatz_block = match.group(2).strip()
    return leitsatz_block


# -------------------
# KI-Schnittstelle mit Fallback
# -------------------
def call_openai(text: str, model: str = DEFAULT_MODEL) -> str:
    models = [model, "gpt-5-mini", "gpt-5"]

    for m in models:
        try:
            print(f"➡️ Versuche Modell: {m}")
            response = client.chat.completions.create(
                model=m,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Fasse den folgenden Urteilstext des Bundesfinanzhofs in höchstens 8 Sätzen "
                            "verständlich zusammen. Konzentriere dich ausschließlich auf die wesentlichen "
                            "steuerrechtlichen Aussagen und das Ergebnis. Schreibe neutral und knapp."
                        ),
                    },
                    {"role": "user", "content": text},
                ],
            )
            content = response.choices[0].message.content.strip()
            if content:
                return content  # ⚠️ Änderung: Erfolgreiche Antwort sofort zurückgeben
            else:
                print(f"⚠️ Modell {m} lieferte keine verwertbare Antwort.")
        except Exception as e:
            print(f"⚠️ Fehler mit Modell {m}: {e}")

    return "⚠️ Keine Antwort von den Modellen erhalten"


def estimate_cost(num_decisions: int, model: str) -> float:
    """Schätzt die Kosten pro Woche (USD)"""
    if model not in PRICES:
        return 0.0
    input_tokens = num_decisions * 2000
    output_tokens = num_decisions * 500
    price_in = PRICES[model]["input"] / 1_000_000
    price_out = PRICES[model]["output"] / 1_000_000
    cost = input_tokens * price_in + output_tokens * price_out
    return round(cost, 4)


# -------------------
# Hauptlogik
# -------------------
def main():
    FEED_URL = "https://www.bundesfinanzhof.de/de/precedent.rss"  # aktueller RSS-Feed
    feed = feedparser.parse(FEED_URL)

    summaries = []
    for entry in feed.entries:
        pdf_link = None
        # HTML-Seite aufrufen und PDF-Link finden
        try:
            r = requests.get(entry.link)
            soup = BeautifulSoup(r.text, "html.parser")
            pdf_tag = soup.find("a", href=True, text=re.compile("PDF", re.I))
            if pdf_tag:
                pdf_link = "https://www.bundesfinanzhof.de" + pdf_tag["href"]
        except Exception as e:
            print(f"⚠️ Konnte PDF-Link nicht laden: {e}")

        if not pdf_link:
            continue

        pdf_path = download_pdf(pdf_link)
        text = extract_text_from_pdf(pdf_path)
        leitsaetze = extract_leitsaetze(text)
        summary = call_openai(text, model=DEFAULT_MODEL)

        summaries.append({
            "title": entry.title,
            "published": entry.published,
            "link": entry.link,
            "leitsaetze": leitsaetze,
            "summary": summary,
        })

    # Wochen-PDF erzeugen
    os.makedirs("weekly_reports", exist_ok=True)
    filename = f"weekly_reports/BFH_Entscheidungen_KW{datetime.now().isocalendar()[1]}_{datetime.now().year}.pdf"
    create_weekly_pdf(summaries, filename, DEFAULT_MODEL)


if __name__ == "__main__":
    main()
