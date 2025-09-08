# BFH-Entscheidungen – Automatisierte Zusammenfassungen & Wochenbericht (PDF)

Dieses Projekt ruft wöchentlich die neuesten Entscheidungen des **Bundesfinanzhofs (BFH)** ab, lädt die Volltext-PDFs herunter, extrahiert den Text und erzeugt **narrative Kurzfassungen** über die OpenAI-API.  
Zum Schluss werden alle Entscheidungen der Woche in einem **formalen Wochen-PDF** (Titelseite inkl. Kalenderwoche/Jahr, Aktenzeichen je Fall, technischer Hinweisblock mit Modellname & Kostenabschätzung) zusammengeführt.  
Optional wird das Wochen-PDF **automatisch per E-Mail** versendet (SMTP).

---

## ✨ Features
- Abruf der neuesten BFH-Entscheidungen via RSS
- PDF-Download & Textextraktion
- Narrative 2-Absatz-Zusammenfassung per OpenAI-API (Modell frei wählbar via ENV `MODEL`)
- Wöchentliches PDF mit Titelseite (formal), Aktenzeichen vor jedem Titel
- „Technische Hinweise“: verwendetes Modell + geschätzte API-Kosten (pro Woche)
- Optionaler **Mailversand** des Wochen-PDFs aus GitHub Actions

---

## 📂 Struktur
.
├─ .github/workflows/fetch_bfh.yml # CI-Workflow: wöchentlicher Lauf + Mailversand
├─ fetch_bfh.py # Hauptskript
├─ requirements.txt # Dependencies
├─ downloads/ # (auto) Original-PDFs
├─ summaries/ # (auto) Markdown-Zusammenfassungen je Entscheidung
└─ weekly_reports/ # (auto) Wochen-PDF (KW_xx_JJJJ)
