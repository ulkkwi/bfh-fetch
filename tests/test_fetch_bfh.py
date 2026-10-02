# tests/test_fetch_bfh.py
# Prüft die Logik von fetch_bfh.py ohne Netzwerk und ohne echte API-Aufrufe.
import os
import sys
import tempfile
import types

try:
    import httpx2 as httpx  # openai ab 3.x
except ImportError:
    import httpx
from bs4 import BeautifulSoup
from openai import AuthenticationError, RateLimitError
from pypdf import PdfReader

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root not in sys.path:
    sys.path.insert(0, root)

import fetch_bfh as fb
from generate_weekly_report import format_published

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "bfh_detail.html")
REQUEST = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
PDF_TEXT = "BUNDESFINANZHOF Urteil vom 1.7.2026, VI R 4/23 Leitsatz: Ein Satz. Tenor: Die Revision wird zurückgewiesen."

def load_fixture():
    with open(FIXTURE, encoding="utf-8") as f:
        return BeautifulSoup(f.read(), "html.parser")

def quota_error(**kwargs):
    raise RateLimitError("no credits", response=httpx.Response(429, request=REQUEST),
                         body={"message": "no credits", "type": "insufficient_quota",
                               "code": "credit_balance_exhausted"})

def auth_error(**kwargs):
    raise AuthenticationError("bad key", response=httpx.Response(401, request=REQUEST),
                              body={"message": "bad key", "type": "invalid_request_error",
                                    "code": "invalid_api_key"})

def ok_response(**kwargs):
    usage = types.SimpleNamespace(prompt_tokens=10_000, completion_tokens=500)
    choice = types.SimpleNamespace(finish_reason="stop",
                                   message=types.SimpleNamespace(content="Kurzfassung."))
    return types.SimpleNamespace(choices=[choice], usage=usage)

class FakeClient:
    def __init__(self, handler):
        self.calls = 0
        def create(**kwargs):
            self.calls += 1
            return handler(**kwargs)
        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=create))

def run_main(handler, workdir, fail_download_for=()):
    """Startet main() mit drei Feed-Einträgen und ersetzt Netzwerk und API durch Stubs."""
    E = types.SimpleNamespace
    published = "Thu, 01 Oct 2026 10:00:01 +0200"
    entries = [E(title="II B 87/25", link=f"https://example.org/{i}",
                 get=lambda k, d="": {"published": published,
                                      "summary": "Nachweis des niedrigeren gemeinen Werts"}.get(k, d))
               for i in range(3)]
    fb.feedparser.parse = lambda url: E(entries=entries)
    parsed = fb.parse_decision_html(load_fixture())
    def fetch(url):
        if url in fail_download_for:
            raise RuntimeError("404")
        return parsed
    fb.fetch_decision = fetch
    fake = FakeClient(handler)
    fb._client = fake

    out = os.path.join(workdir, "github_output.txt")
    open(out, "w").close()
    os.environ["GITHUB_OUTPUT"] = out
    cwd = os.getcwd()
    os.chdir(workdir)
    exit_code = 0
    try:
        fb.main()
    except SystemExit as e:
        exit_code = e.code
    finally:
        os.chdir(cwd)

    report_dir = os.path.join(workdir, "weekly_reports")
    pdf = os.path.join(report_dir, os.listdir(report_dir)[0])
    text = "".join(p.extract_text() for p in PdfReader(pdf).pages)
    return exit_code, fake.calls, open(out).read(), text

def test_helpers():
    assert format_published("Thu, 01 Oct 2026 10:00:02 +0200") == "01.10.2026, 10:00 Uhr"
    assert format_published("Thu, 01 Oct 2026 08:00:02 +0000") == "01.10.2026, 10:00 Uhr"
    assert fb.extract_case_number("Urteil vom 1.7.2026, VI R 4/23") == "VI R 4/23"
    assert fb.extract_case_number("XI B 120/24 Beschluss") == "XI B 120/24"
    assert fb.extract_case_number("Keine Nummer 2026") == ""
    assert fb.title_with_case_number("VI R 4/23 – Titel", "IX R 1/22") == "VI R 4/23 – Titel"
    assert fb.title_with_case_number("Titel", PDF_TEXT) == "VI R 4/23: Titel"
    assert fb.extract_leitsatz(PDF_TEXT) == "Ein Satz."

def test_parse_html():
    d = fb.parse_decision_html(load_fixture())
    assert d is not None and d["source"] == "html"
    assert d["decision"] == "Beschluss vom 04. August 2026, BFH II. Senat"
    assert d["topic"].startswith("Nachweis des niedrigeren gemeinen Werts")
    assert d["leitsatz"].startswith("Eine pauschale Zurückweisung")
    assert d["leitsatz"].endswith("--FGO--).")  # geschützte Bindestriche vereinheitlicht
    assert "Tenor" not in d["leitsatz"]
    assert "Die Beschwerde ist begründet." in d["text"]
    assert "zurück zur Übersicht" not in d["text"]
    assert "§ 198 Abs 2 BewG,\n§ 76 Abs 1 S 1 FGO" in d["text"]  # Leerraum bereinigt
    # Aktenzeichen mit Klammerzusatz (Hotel-Urteile vom 21.05.2026)
    soup = load_fixture()
    soup.select_one("div.m-article__header h1").string = "Urteil vom 21. Mai 2026, V R 8/26 (XI R 11/23, XI R 34/20)"
    assert fb.parse_decision_html(soup)["decision"] == "Urteil vom 21. Mai 2026, BFH II. Senat"
    # unbekannter Seitenaufbau -> None, dann wird das PDF verwendet
    assert fb.parse_decision_html(BeautifulSoup("<html><body><p>x</p></body></html>", "html.parser")) is None
    assert fb.find_pdf_url(load_fixture(), "https://www.bundesfinanzhof.de/de/x/").endswith("STRE202610181?type=1646225765")
    assert fb.model_order("gpt-5-nano") == ["gpt-5-nano", "gpt-5-mini", "gpt-5"]
    assert fb.model_order("gpt-5-mini") == ["gpt-5-mini", "gpt-5"]
    assert fb.model_order("anderes") == ["anderes", "gpt-5-nano", "gpt-5-mini", "gpt-5"]

def test_normal_run():
    with tempfile.TemporaryDirectory() as d:
        code, calls, output, text = run_main(ok_response, d, fail_download_for=("https://example.org/2",))
    assert code == 0 and calls == 2 and output == ""
    assert "II B 87/25: Nachweis des niedrigeren gemeinen Werts" in text
    assert "Beschluss vom 04. August 2026, BFH II. Senat" in text
    assert "01.10.2026, 10:00 Uhr" in text
    assert "Volltext konnte nicht geladen werden" in text
    assert "gpt-5-mini" in text and "0,0070 USD" in text

def test_quota_exhausted():
    with tempfile.TemporaryDirectory() as d:
        code, calls, output, text = run_main(quota_error, d)
    assert code == 1
    assert calls == 1, f"nach dem ersten Fehler keine weiteren Aufrufe, waren aber {calls}"
    assert "Guthaben aufgebraucht" in output
    assert "Guthaben für die OpenAI-API ist aufgebraucht" in text
    assert "Eine pauschale Zurückweisung" in text  # Leitsätze bleiben erhalten

def test_invalid_key():
    with tempfile.TemporaryDirectory() as d:
        code, calls, output, text = run_main(auth_error, d)
    assert code == 1 and calls == 1
    assert "Schlüssel ungültig" in output
    assert "API-Schlüssel ist ungültig" in text

def main():
    tests = [test_helpers, test_parse_html, test_normal_run, test_quota_exhausted, test_invalid_key]
    for t in tests:
        t()
        print(f"✅ {t.__name__}")
    print("✅ Alle Tests erfolgreich.")

if __name__ == "__main__":
    main()
