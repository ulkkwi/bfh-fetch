# generate_weekly_report.py
import os
import re
from datetime import datetime, date
from email.utils import parsedate_to_datetime
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import pyphen

# --- sichere Registrierung der DejaVuSans-Schrift ---
font_path = os.path.join(os.path.dirname(__file__), "fonts", "DejaVuSans.ttf")
FONT_NAME = "DejaVuSans"
font_registered = False

if os.path.exists(font_path):
    try:
        pdfmetrics.registerFont(TTFont(FONT_NAME, font_path))
        font_registered = True
    except Exception as e:
        print(f"⚠️ Fehler beim Registrieren der lokalen DejaVuSans.ttf: {e}")

if not font_registered:
    # versuche einen systemweiten DejaVuSans.ttf (nur wenn vorhanden)
    try:
        pdfmetrics.registerFont(TTFont(FONT_NAME, "DejaVuSans.ttf"))
        font_registered = True
    except Exception:
        print("ℹ️ DejaVuSans nicht gefunden; Fallback auf Helvetica wird verwendet.")
# --- Ende Font-Block ---

# Hyphenator
dic = pyphen.Pyphen(lang="de_DE")

def hyphenate_text(text: str, min_len: int = 12) -> str:
    """
    Fügt in langen Wörtern ASCII-Bindestriche an möglichen Trennstellen ein.
    Keine Soft-Hyphen (U+00AD) — damit kein Kästchen bei fehlender Glyph.
    """
    def hyphenate_word(w: str) -> str:
        # Nur Wörter mit Buchstaben hyphenisieren, Zahlen oder URLs ignorieren
        if len(w) <= min_len:
            return w
        if re.search(r"[A-Za-zÄÖÜäöüß]", w) is None:
            return w
        try:
            return dic.inserted(w, hyphen="-")
        except Exception:
            return w

    # Bewahre Satzzeichen am Ende (z.B. "Wort,"), hyphenate_word nur am reinen Wort anwenden
    parts = re.split(r"(\s+)", text)  # Whitespace erhalten
    out = []
    for token in parts:
        if token.isspace() or token == "":
            out.append(token)
        else:
            # Trenne evtl. angehängte Satzzeichen ab
            m = re.match(r"^([^\wÄÖÜäöüß\-]*)(.+?)([^\wÄÖÜäöüß\-]*)$", token, re.UNICODE)
            if m:
                pref, core, suf = m.groups()
                out.append(pref + hyphenate_word(core) + (suf or ""))
            else:
                out.append(hyphenate_word(token))
    return "".join(out)

def create_weekly_pdf(summaries, filename, model):
    doc = SimpleDocTemplate(filename, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()

    font_to_use = FONT_NAME if font_registered else "Helvetica"

    # Deutscher Blocksatz-Stil (Zeilenumbruch nur an Whitespace oder an eingefügten Bindestrichen)
    german_style = ParagraphStyle(
        "German",
        parent=styles["Normal"],
        alignment=TA_JUSTIFY,
        leading=14,
        fontName=font_to_use,
        wordWrap="LTR",  # LTR: break at whitespace or hyphen, kein CJK-Verhalten
    )

    story = []
    today = date.today()
    year, week, _ = datetime.now().isocalendar()

    # ---- Titelseite ----
    story.append(Spacer(1, 5 * cm))
    story.append(Paragraph("<para align='center'><b>Bundesfinanzhof</b></para>", styles["Title"]))
    story.append(Spacer(1, 1 * cm))
    story.append(Paragraph("<para align='center'>Wochenbericht zu aktuellen Entscheidungen</para>", styles["Title"]))
    story.append(Spacer(1, 3 * cm))

    data = [
        ["Kalenderwoche:", f"{week} / {year}"],
        ["Erstellt am:", today.strftime("%d.%m.%Y")],
    ]
    table = Table(data, colWidths=[5 * cm, 10 * cm])
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("FONT", (0, 0), (-1, -1), font_to_use, 12),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
    ]))
    story.append(table)
    story.append(PageBreak())

    # ---- Inhalt ----
    story.append(Paragraph("<b>Zusammenfassungen der Entscheidungen</b>", styles["Heading1"]))
    story.append(Spacer(1, 20))

    for entry in summaries:
        # Titel: Aktenzeichen + restlicher Titel (falls Aktenzeichen vorhanden)
        story.append(Paragraph(f"<b>{entry.get('title','Unbekannte Entscheidung')}</b>", styles["Heading2"]))

        # Veröffentlichungsdatum robust parsen (funktioniert mit RFC-2822/ RSS-Dates)
        pub = entry.get("published", "")
        pub_date_str = pub
        try:
            dt = parsedate_to_datetime(pub)
            # Wenn tzinfo vorhanden, in lokale Zeit umwandeln
            try:
                dt = dt.astimezone()
            except Exception:
                pass
            pub_date_str = dt.strftime("%d.%m.%Y, %H:%M Uhr")
        except Exception:
            # leave original if parsing fails
            pub_date_str = pub

        story.append(Paragraph(f"Veröffentlicht: {pub_date_str}", styles["Normal"]))
        story.append(Paragraph(f"Link: <a href='{entry.get('link','')}'>{entry.get('link','')}</a>", styles["Normal"]))
        story.append(Spacer(1, 10))

        # Leitsatz (falls vorhanden) — Hyphenation anwenden
        leitsatz = entry.get("leitsatz", "")
        if leitsatz:
            story.append(Paragraph("<b>Leitsätze:</b>", styles["Heading3"]))
            story.append(Paragraph(hyphenate_text(leitsatz), german_style))
            story.append(Spacer(1, 10))

        # Zusammenfassung — Hyphenation anwenden
        summary = entry.get("summary", "")
        if summary:
            story.append(Paragraph("<b>Kurz-Zusammenfassung:</b>", styles["Heading3"]))
            story.append(Paragraph(hyphenate_text(summary), german_style))
            story.append(Spacer(1, 20))

    # ---- Technischer Hinweis ----
    story.append(PageBreak())
    story.append(Paragraph("<b>Technische Hinweise</b>", styles["Heading1"]))
    story.append(Spacer(1, 10))
    story.append(Paragraph(f"Die Zusammenfassungen wurden automatisch mit dem Modell <b>{model}</b> erstellt.", styles["Normal"]))
    story.append(Spacer(1, 10))
    story.append(Paragraph("Quelle: RSS-Feed des Bundesfinanzhofs.", styles["Normal"]))

    doc.build(story)
    print(f"📄 Wochen-PDF erstellt: {filename}")
