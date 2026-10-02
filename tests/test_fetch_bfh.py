# tests/test_fetch_bfh.py
# Prüft die Logik von fetch_bfh.py ohne Netzwerk und ohne echte API-Aufrufe.
import os
import sys
import tempfile
import types

import httpx
from openai import AuthenticationError, RateLimitError
from pypdf import PdfReader

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root not in sys.path:
    sys.path.insert(0, root)

import fetch_bfh as fb
from generate_weekly_report import format_published

REQUEST = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
PDF_TEXT = "BUNDESFINANZHOF Urteil vom 1.7.2026, VI R 4/23 Leitsatz: Ein Satz. Tenor: Die Revision wird zurückgewiesen."

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
    entries = [E(title=f"Einkommensteuer Fall {i}", published="Thu, 01 Oct 2026 10:00:02 +0200",
                 link=f"https://example.org/{i}", get=lambda k, d="": "Thu, 01 Oct 2026 10:00:02 +0200")
               for i in range(3)]
    fb.feedparser.parse = lambda url: E(entries=entries)
    fb.build_bfh_pdf_url = lambda link: link
    def download(url):
        if url in fail_download_for:
            raise RuntimeError("404")
        return "dummy.pdf"
    fb.download_pdf = download
    fb.extract_text_from_pdf = lambda path: PDF_TEXT
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
    assert fb.title_with_case_number("Titel", PDF_TEXT) == "VI R 4/23 – Titel"
    assert fb.extract_leitsatz(PDF_TEXT) == "Ein Satz."
    assert fb.model_order("gpt-5-nano") == ["gpt-5-nano", "gpt-5-mini", "gpt-5"]
    assert fb.model_order("gpt-5-mini") == ["gpt-5-mini", "gpt-5"]
    assert fb.model_order("anderes") == ["anderes", "gpt-5-nano", "gpt-5-mini", "gpt-5"]

def test_normal_run():
    with tempfile.TemporaryDirectory() as d:
        code, calls, output, text = run_main(ok_response, d, fail_download_for=("https://example.org/2",))
    assert code == 0 and calls == 2 and output == ""
    assert "VI R 4/23 – Einkommensteuer Fall 0" in text
    assert "01.10.2026, 10:00 Uhr" in text
    assert "Volltext konnte nicht geladen werden" in text
    assert "gpt-5-nano" in text and "0,0014 USD" in text

def test_quota_exhausted():
    with tempfile.TemporaryDirectory() as d:
        code, calls, output, text = run_main(quota_error, d)
    assert code == 1
    assert calls == 1, f"nach dem ersten Fehler keine weiteren Aufrufe, waren aber {calls}"
    assert "Guthaben aufgebraucht" in output
    assert "Guthaben für die OpenAI-API ist aufgebraucht" in text
    assert "Ein Satz." in text  # Leitsätze bleiben erhalten

def test_invalid_key():
    with tempfile.TemporaryDirectory() as d:
        code, calls, output, text = run_main(auth_error, d)
    assert code == 1 and calls == 1
    assert "Schlüssel ungültig" in output
    assert "API-Schlüssel ist ungültig" in text

def main():
    tests = [test_helpers, test_normal_run, test_quota_exhausted, test_invalid_key]
    for t in tests:
        t()
        print(f"✅ {t.__name__}")
    print("✅ Alle Tests erfolgreich.")

if __name__ == "__main__":
    main()
