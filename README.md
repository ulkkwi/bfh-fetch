# BFH-Entscheidungen – Automatisierte Zusammenfassungen & Wochenbericht (PDF)

Dieses Projekt ruft wöchentlich die neuesten Entscheidungen des **Bundesfinanzhofs (BFH)** ab, extrahiert den Text und erzeugt **narrative Kurzfassungen** über die OpenAI-API.  
Zum Schluss werden alle Entscheidungen der Woche in einem **formalen Wochen-PDF** (Titelseite inkl. Kalenderwoche/Jahr, Aktenzeichen je Fall, technischer Hinweisblock mit Modellname & API-Kosten) zusammengeführt.  
Das Wochen-PDF wird **automatisch per E-Mail** versendet (SMTP).

---

## ✨ Features
- Abruf der neuesten BFH-Entscheidungen via RSS
- Textextraktion von der Detailseite des BFH (Leitsätze und Volltext)
- Narrative Zusammenfassung per OpenAI-API (ein Absatz, höchstens 5 Sätze)
  - Standardmodell `gpt-5-mini`, wählbar über das Secret `MODEL`
  - Liefert das Modell keine Antwort, wird `gpt-5` versucht
- Wöchentliches PDF mit Titelseite (formal), je Entscheidung Aktenzeichen, Thema, Art, Datum und Senat
- „Technische Hinweise“: tatsächlich verwendete Modelle + angefallene API-Kosten
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
