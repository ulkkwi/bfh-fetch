import os
import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urljoin

import feedparser
import requests
from bs4 import BeautifulSoup
from openai import OpenAI, APIError, AuthenticationError
from pypdf import PdfReader

from generate_weekly_report import create_weekly_pdf

# -------------------
# Konfiguration
# -------------------
DEFAULT_MODEL = os.getenv("MODEL", "gpt-5-nano")  # Startmodell aus Umgebungsvariable oder Default

# Reihenfolge der Ausweichmodelle, falls ein Modell keine Antwort liefert
FALLBACK_MODELS = ["gpt-5-nano", "gpt-5-mini", "gpt-5"]

# Preise pro 1M Tokens (USD) – Stand 2025
PRICES = {
    "gpt-5-nano": {"input": 0.05, "output": 0.40},
    "gpt-5-mini": {"input": 0.25, "output": 2.00},
    "gpt-5": {"input": 1.25, "output": 10.00},
}

# Obergrenze für den Volltext pro Entscheidung (ca. 75.000 Tokens).
# Die Modelle verarbeiten deutlich mehr, die Grenze schützt nur vor Ausreißern.
MAX_INPUT_CHARS = 300_000

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}

SYSTEM_PROMPT = (
    "Du bist ein juristischer Assistent. "
    "Fasse die folgende Entscheidung des Bundesfinanzhofs in EINEM klaren Absatz zusammen. "
    "Konzentriere dich auf den Kern der Entscheidung. "
    "Maximal 5 Sätze, keine Fußnoten, keine Zitate."
)

QUOTA_MESSAGE = (
    "Keine Zusammenfassung erstellt: Das Guthaben für die OpenAI-API ist aufgebraucht. "
    "Bitte unter https://platform.openai.com/settings/organization/billing/ aufladen."
)
AUTH_MESSAGE = (
    "Keine Zusammenfassung erstellt: Der OpenAI-API-Schlüssel ist ungültig oder fehlt. "
    "Bitte das Secret OPENAI_API_KEY im GitHub-Repository prüfen."
)

_client = None

def get_client() -> OpenAI:
    """Erzeugt den OpenAI-Client erst bei Bedarf.
    Vorübergehende Fehler (Netzwerk, Überlast) wiederholt der Client selbst
    mit demselben Modell, bevor auf ein anderes Modell ausgewichen wird."""
    global _client
    if _client is None:
        _client = OpenAI(max_retries=4, timeout=300)
    return _client

class FatalAPIError(Exception):
    """Die API ist nicht nutzbar (kein Guthaben, ungültiger Schlüssel), weitere Aufrufe sind zwecklos."""
    def __init__(self, message: str, reason: str, notice: str):
        super().__init__(message)
        self.reason = reason  # Kurztext für den Mail-Betreff
        self.notice = notice  # Hinweis im PDF

def is_quota_error(e: Exception) -> bool:
    return isinstance(e, APIError) and (
        e.code in ("insufficient_quota", "credit_balance_exhausted")
        or e.type == "insufficient_quota"
    )

def model_order(start_model: str) -> list[str]:
    """Startmodell zuerst, danach nur die größeren Ausweichmodelle."""
    if start_model in FALLBACK_MODELS:
        return FALLBACK_MODELS[FALLBACK_MODELS.index(start_model):]
    return [start_model] + FALLBACK_MODELS

class UsageTracker:
    """Sammelt die tatsächlich verwendeten Modelle und Token für die Kostenangabe."""
    def __init__(self):
        self.tokens = {}  # Modell -> [input, output]

    def add(self, model: str, usage):
        if usage is None:
            return
        t = self.tokens.setdefault(model, [0, 0])
        t[0] += usage.prompt_tokens or 0
        t[1] += usage.completion_tokens or 0

    @property
    def models(self) -> list[str]:
        return list(self.tokens)

    def cost(self) -> float | None:
        """Kosten in USD, None wenn für ein Modell kein Preis hinterlegt ist."""
        total = 0.0
        for model, (tin, tout) in self.tokens.items():
            if model not in PRICES:
                return None
            total += tin * PRICES[model]["input"] / 1_000_000
            total += tout * PRICES[model]["output"] / 1_000_000
        return total

# -------------------
# Hilfsfunktionen
# -------------------
CASE_NUMBER_RE = re.compile(r"\b(?:[IVX]{1,4}|GrS)\s+[A-Z]{1,2}\s+\d+/\d{2}\b")

def extract_case_number(text: str) -> str:
    """Extrahiert das Aktenzeichen (z. B. VI R 4/23), leer wenn keins gefunden"""
    match = CASE_NUMBER_RE.search(text)
    return match.group(0) if match else ""

def title_with_case_number(title: str, pdf_text: str) -> str:
    """Stellt das Aktenzeichen aus dem PDF vor den Titel, falls es dort noch fehlt."""
    if extract_case_number(title):
        return title
    case_number = extract_case_number(pdf_text[:3000])
    return f"{case_number} – {title}" if case_number else title

def build_bfh_pdf_url(detail_url: str) -> str:
    """
    Ermittelt den echten PDF-Link direkt von der normalen Detailseite.
    Sucht <a> mit /detail/pdf/... und behält den ?type=... Parameter bei.
    """
    # 1) Original-Detailseite laden (kein /pdf/ anhängen!)
    resp = requests.get(detail_url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # 2) Kandidaten sammeln: alle <a href> mit "/detail/pdf/"
    candidates = [a for a in soup.find_all("a", href=True) if "/detail/pdf/" in a["href"]]

    if not candidates:
        # Optionaler Fallback: Seite /pdf/ probieren, falls BFH-Seitenstruktur abweicht
        pdf_overview_url = detail_url.rstrip("/") + "/pdf/"
        resp2 = requests.get(pdf_overview_url, headers=HEADERS, timeout=20)
        if resp2.ok:
            soup2 = BeautifulSoup(resp2.text, "html.parser")
            candidates = [a for a in soup2.find_all("a", href=True) if "/detail/pdf/" in a["href"]]

    if not candidates:
        raise RuntimeError(f"Kein PDF-Link auf {detail_url} gefunden")

    # 3) Bester Treffer: bevorzugt Download-Link mit Klasse/Titel/Text „PDF“ und vorhandenen ?type=
    def score(a):
        s = 0
        cls = " ".join(a.get("class", []))
        title = a.get("title", "") or ""
        text = (a.get_text() or "").strip()
        href = a["href"]
        if "a-link--download" in cls:
            s += 3
        if "PDF" in title.upper():
            s += 2
        if "PDF" in text.upper():
            s += 1
        if "type=" in href:
            s += 2
        return s

    best = max(candidates, key=score)
    pdf_url = urljoin(detail_url, best["href"])  # relative -> absolute URL
    print(f"🔗 Gefundener PDF-Link: {pdf_url}")
    return pdf_url

# BFH PDFs sauber benennen (ignoriere ?type=...)
def download_pdf(url: str, folder="downloads"):
    os.makedirs(folder, exist_ok=True)

    basename = url.split("/")[-1].split("?")[0]  # Query-Teil abschneiden
    if not basename.lower().endswith(".pdf"):
        basename = f"{basename}.pdf"

    filename = os.path.join(folder, basename)

    r = requests.get(url, headers=HEADERS, timeout=60)
    r.raise_for_status()
    with open(filename, "wb") as f:
        f.write(r.content)

    return filename

def extract_text_from_pdf(path: str) -> str:
    reader = PdfReader(path)
    return "".join(page.extract_text() or "" for page in reader.pages)

def extract_leitsatz(text: str) -> str:
    """
    Schneidet die Leitsätze bis vor 'Tenor' heraus.
    Erkennt 'Leitsatz' oder 'Leitsätze', mit oder ohne Doppelpunkt.
    """
    m = re.search(r"Leits(?:atz|ätze)\s*:?(.*?)(?=Tenor)", text, re.S | re.I)
    return m.group(1).strip() if m else ""

def summarize_text(text: str, tracker: UsageTracker) -> str:
    """
    Fasst den Volltext mit einem einzigen Aufruf zusammen.
    Liefert ein Modell nichts, wird das nächstgrößere versucht.
    Antworten mit finish_reason="length" werden trotzdem übernommen.
    """
    text = text[:MAX_INPUT_CHARS]

    for model in model_order(DEFAULT_MODEL):
        try:
            print(f"➡️ Zusammenfassung mit Modell: {model}")
            response = get_client().chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
                reasoning_effort="low",
                max_completion_tokens=4000,
            )
            tracker.add(model, response.usage)

            finish_reason = response.choices[0].finish_reason
            content = (response.choices[0].message.content or "").strip()
            print(f"🔎 Finish reason: {finish_reason}")

            if content:
                if finish_reason == "length":
                    print("✂️ Antwort war abgeschnitten, Teiltext wird übernommen.")
                return content
            print(f"⚠️ Modell {model} hat nichts geliefert, versuche nächstes...")

        except AuthenticationError as e:
            raise FatalAPIError(str(e), "OpenAI-API-Schlüssel ungültig", AUTH_MESSAGE) from e
        except Exception as e:
            if is_quota_error(e):
                raise FatalAPIError(str(e), "OpenAI-Guthaben aufgebraucht", QUOTA_MESSAGE) from e
            print(f"⚠️ Fehler mit Modell {model}: {e}")

    return "⚠️ Keine Antwort vom Modell erhalten."

def write_github_output(key: str, value: str):
    github_output = os.getenv("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"{key}={value}\n")

# -------------------
# Hauptlogik
# -------------------
def main():
    FEED_URL = "https://www.bundesfinanzhof.de/de/precedent.rss"
    feed = feedparser.parse(FEED_URL)

    # Testmodus aus GitHub Actions
    test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
    if test_mode:
        print("🧪 Testmodus aktiv: nur 1 Entscheidung wird verarbeitet")
        feed.entries = feed.entries[:1]

    tracker = UsageTracker()
    summaries = []
    fatal = None  # FatalAPIError, sobald die API nicht mehr nutzbar ist

    for entry in feed.entries:
        item = {
            "title": entry.title,
            "published": entry.get("published", ""),
            "link": entry.link,
            "leitsatz": "",
            "summary": "",
        }
        summaries.append(item)

        try:
            pdf_link = build_bfh_pdf_url(entry.link)
            pdf_path = download_pdf(pdf_link)
            raw_text = extract_text_from_pdf(pdf_path)
        except Exception as e:
            print(f"⚠️ Volltext für {entry.link} nicht verfügbar: {e}, überspringe...")
            item["summary"] = "⚠️ Der Volltext konnte nicht geladen werden, siehe Link."
            continue

        item["title"] = title_with_case_number(entry.title, raw_text)
        item["leitsatz"] = extract_leitsatz(raw_text)

        if fatal is None:
            try:
                item["summary"] = summarize_text(raw_text, tracker)
            except FatalAPIError as e:
                print(f"❌ {e.reason}, keine weiteren API-Aufrufe: {e}")
                fatal = e
        if fatal is not None:
            item["summary"] = fatal.notice

    os.makedirs("weekly_reports", exist_ok=True)
    year, week, _ = datetime.now(ZoneInfo("Europe/Berlin")).isocalendar()
    filename = f"weekly_reports/BFH_Entscheidungen_KW{week}_{year}.pdf"

    warning = fatal.notice if fatal is not None else None
    create_weekly_pdf(summaries, filename, tracker.models, cost=tracker.cost(), warning=warning)

    if fatal is not None:
        # Hinweis für den Mail-Schritt im Workflow
        write_github_output("warning", f"{fatal.reason}, Zusammenfassungen fehlen")
        sys.exit(1)

if __name__ == "__main__":
    main()
