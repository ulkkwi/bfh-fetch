# BFH-Entscheidungen – Automatisierte Zusammenfassungen & Wochenbericht (PDF)

Dieses Projekt ruft wöchentlich die neuesten Entscheidungen des **Bundesfinanzhofs (BFH)** ab, liest die Volltexte von der Website des BFH und erzeugt **Kurzfassungen** über die OpenAI-API.  
Zum Schluss werden alle Entscheidungen der Woche in einem **Wochen-PDF** zusammengeführt (Titelseite mit Kalenderwoche/Jahr, Aktenzeichen je Fall, technische Hinweise mit Modellname und API-Kosten).  
Das Wochen-PDF wird **automatisch per E-Mail** versendet (SMTP).

---

## ✨ Features
- Abruf der neuesten BFH-Entscheidungen via RSS
- Volltext und Leitsätze direkt von der Detailseite des BFH (HTML), das PDF dient nur als Rückfallebene
- Bericht zeigt je Entscheidung Aktenzeichen, Thema, Art, Datum und Senat
- Kurzfassung je Entscheidung (ein Absatz, höchstens 5 Sätze) per OpenAI-API
  - Startmodell über das Secret `MODEL` wählbar (Standard: `gpt-5-mini`)
  - Liefert ein Modell keine Antwort, wird das nächstgrößere versucht (`gpt-5`)
- Wöchentliches PDF mit Titelseite, Aktenzeichen vor jedem Titel
- „Technische Hinweise“: tatsächlich verwendete Modelle und angefallene API-Kosten
- **Mailversand** des Wochen-PDFs aus GitHub Actions

## ⚠️ Fehlerfälle
- **OpenAI-Guthaben aufgebraucht oder API-Schlüssel ungültig:** Es werden keine weiteren API-Aufrufe gemacht. Der Bericht wird mit den Leitsätzen und einem deutlichen Hinweis trotzdem verschickt, der Betreff der Mail enthält „ACHTUNG“ und der Workflow wird rot.
- **Volltext einer Entscheidung nicht abrufbar:** Die Entscheidung erscheint mit Link und Hinweis im Bericht, die übrigen werden normal verarbeitet.

## 🧪 Tests
```
pip install -r requirements.txt
python tests/test_fetch_bfh.py
python tests/test_generate_weekly_report.py
```
Die Tests laufen ohne Netzwerk und ohne API-Schlüssel und werden bei jedem Push in GitHub Actions ausgeführt.
