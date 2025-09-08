from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import os

def create_dummy_pdf(filename="weekly_reports/Dummy_Test.pdf"):
    os.makedirs("weekly_reports", exist_ok=True)
    c = canvas.Canvas(filename, pagesize=A4)
    c.setFont("Helvetica", 14)
    c.drawString(100, 750, "📄 Test-PDF für Mailversand")
    c.drawString(100, 720, "Wenn du diese Datei per Mail bekommst,")
    c.drawString(100, 700, "funktioniert dein SMTP-Setup korrekt!")
    c.showPage()
    c.save()
    print(f"✅ Dummy-PDF erstellt: {filename}")

if __name__ == "__main__":
    create_dummy_pdf()
