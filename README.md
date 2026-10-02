# BFH-Entscheidungen – Automatisierte Zusammenfassungen & Wochenbericht (PDF)

Dieses Projekt ruft wöchentlich die neuesten Entscheidungen des **Bundesfinanzhofs (BFH)** ab, extrahiert den Text und erzeugt **narrative Kurzfassungen** über die OpenAI-API.  
Zum Schluss werden alle Entscheidungen der Woche in einem **formalen Wochen-PDF** (Titelseite inkl. Kalenderwoche/Jahr, Aktenzeichen je Fall, technischer Hinweisblock mit Modellname & Kostenabschätzung) zusammengeführt.  
Das Wochen-PDF wird **automatisch per E-Mail** versendet (SMTP).

---

## ✨ Features
- Abruf der neuesten BFH-Entscheidungen via RSS
- Textextraktion
- Narrative 2-Absatz-Zusammenfassung per OpenAI-API (Modell frei wählbar via ENV `MODEL`)
- Wöchentliches PDF mit Titelseite (formal), Aktenzeichen vor jedem Titel
- „Technische Hinweise“: verwendetes Modell + geschätzte API-Kosten (pro Woche)
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
