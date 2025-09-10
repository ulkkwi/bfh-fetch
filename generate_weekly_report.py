import locale
from datetime import datetime, date
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os

# DejaVuSans für Umlaute und Bindestriche registrieren
font_path = os.path.join(os.path.dirname(__file__), "fonts", "DejaVuSans.ttf")
if os.path.exists(font_path):
    pdfmetrics.registerFont(TTFont("DejaVuSans", font_path))
else:
    # Fallback, falls Font nicht vorhanden
    pdfmetrics.registerFont(TTFont("DejaVuSans", "DejaVuSans.ttf"))

# Deutsche Lokalisierung für Datum
try:
    locale.setlocale(locale.LC_TIME, "de_DE.UTF-8")
except locale.Error:
    # Fallback für Umgebungen ohne deutsches Locale
    locale.setlocale(locale.LC_TIME, "C")


def create_weekly_pdf(summaries, filename, model):
    doc = SimpleDocTemplate(filename, pagesize=A4)
    styles = getSampleStyleSheet()

    # Deutscher Blocksatz-Stil mit Zeilenumbruch am Wortende
    german_style = ParagraphStyle(
        "German",
        parent=styles["Normal"],
        alignment=TA_JUSTIFY,
        leading=14,
        fontName="DejaVuSans",
        wordWrap="CJK",  # sorgt für korrekte Trennung am Zeilenende
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
        ("FONT", (0, 0), (-1, -1), "Helvetica", 12),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
    ]))
    story.append(table)
    story.append(PageBreak())

    # ---- Inhalt ----
    story.append(Paragraph("<b>Zusammenfassungen der Entscheidungen</b>", styles["Heading1"]))
    story.append(Spacer(1, 20))

    for entry in summaries:
        story.append(Paragraph(f"<b>{entry['title']}</b>", styles["Heading2"]))

        # Veröffentlichungsdatum auf Deutsch formatieren
        try:
            pub_date = datetime.strptime(entry["published"], "%a, %d %b %Y %H:%M:%S %z")
            pub_date_str = pub_date.strftime("%d.%m.%Y, %H:%M Uhr")
        except Exception:
            pub_date_str = entry["published"]

        story.append(Paragraph(f"Veröffentlicht: {pub_date_str}", styles["Normal"]))
        story.append(Paragraph(f"Link: <a href='{entry['link']}'>{entry['link']}</a>", styles["Normal"]))
        story.append(Spacer(1, 10))

        if entry.get("leitsatz"):
            story.append(Paragraph("<b>Leitsätze:</b>", styles["Heading3"]))
            story.append(Paragraph(entry["leitsatz"], german_style))
            story.append(Spacer(1, 10))

        if entry.get("summary"):
            story.append(Paragraph("<b>Kurz-Zusammenfassung:</b>", styles["Heading3"]))
            story.append(Paragraph(entry["summary"], german_style))
            story.append(Spacer(1, 20))

    # ---- Technischer Hinweis ----
    story.append(PageBreak())
    story.append(Paragraph("<b>Technische Hinweise</b>", styles["Heading1"]))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        f"Die Zusammenfassungen wurden automatisch mit dem Modell <b>{model}</b> erstellt.",
        styles["Normal"]))
    story.append(Spacer(1, 10))
    story.append(Paragraph("Quelle: RSS-Feed des Bundesfinanzhofs.", styles["Normal"]))

    doc.build(story)
    print(f"📄 Wochen-PDF erstellt: {filename}")
