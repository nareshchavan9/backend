from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, black, white
from io import BytesIO
from datetime import datetime

# Institutional Color Palette
COLOR_MEDICAL_DARK = HexColor('#0F172A')
COLOR_TAN = HexColor('#EDD5B3')
COLOR_SLATE_600 = HexColor('#475569')
COLOR_SLATE_400 = HexColor('#94A3B8')
COLOR_SLATE_100 = HexColor('#F1F5F9')

def generate_pdf_report(prediction_data: dict, user_data: dict, doctor_data: dict = None):
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    cx = width / 2

    # ── Page Border (Institutional) ──────────────────────────────────────────────
    p.setStrokeColor(COLOR_SLATE_100)
    p.setLineWidth(1)
    p.rect(20, 20, width - 40, height - 40)

    # ── Header ───────────────────────────────────────────────────────────────────
    p.setFillColor(COLOR_MEDICAL_DARK)
    p.rect(0, height - 80, width, 80, stroke=0, fill=1)

    p.setFont("Helvetica-Bold", 18)
    p.setFillColor(white)
    p.drawCentredString(cx, height - 45, "HEARTSYNC NEURAL SYSTEMS")
    
    p.setFont("Helvetica", 10)
    p.setFillColor(COLOR_TAN)
    p.drawCentredString(cx, height - 62, "CLINICAL CARDIOVASCULAR DIAGNOSTIC REPORT")

    p.setFont("Helvetica", 8)
    p.setFillColor(white)
    # Correcting the field from 'id' to '_id' to match MongoDB records
    case_id = str(prediction_data.get('_id', 'N/A'))
    p.drawRightString(width - 40, height - 45, f"CASE ID: {case_id[-12:].upper()}")
    p.drawRightString(width - 40, height - 60, datetime.now().strftime('%Y-%m-%d %H:%M'))

    y = height - 120

    # ── Section helper ───────────────────────────────────────────────────────────
    def section_title(title):
        nonlocal y
        y -= 10
        p.setFont("Helvetica-Bold", 9)
        p.setFillColor(COLOR_SLATE_600)
        p.drawString(40, y, title.upper())
        y -= 6
        p.setStrokeColor(COLOR_SLATE_100)
        p.setLineWidth(0.5)
        p.line(40, y, width - 40, y)
        y -= 20

    # ── Subject Information ──────────────────────────────────────────────────────
    section_title("Patient Records")
    
    p.setFont("Helvetica-Bold", 10)
    p.setFillColor(COLOR_MEDICAL_DARK)
    
    col1 = 40
    col2 = cx
    
    info = [
        ("Subject Name", user_data.get('name', 'N/A')),
        ("Clinical ID", user_data.get('email', 'N/A')),
        ("Report Date", datetime.now().strftime('%B %d, %Y')),
        ("Analysis Mode", "Neural Engine v4.2")
    ]
    
    for i, (label, val) in enumerate(info):
        row = i // 2
        col = i % 2
        curr_y = y - row * 35  # Increased row spacing
        curr_x = col1 if col == 0 else col2
        
        p.setFont("Helvetica-Bold", 7)
        p.setFillColor(COLOR_SLATE_400)
        p.drawString(curr_x, curr_y, label.upper())
        
        p.setFont("Helvetica-Bold", 10)
        p.setFillColor(COLOR_MEDICAL_DARK)
        p.drawString(curr_x, curr_y - 14, str(val))
        
    y -= 80  # Adjusted y after records

    # ── Analysis Core ────────────────────────────────────────────────────────────
    section_title("Diagnostic Classification")
    
    is_normal = str(prediction_data.get('prediction', '')).lower() == 'normal'
    
    # Classification Box
    box_h = 85
    p.setStrokeColor(COLOR_SLATE_100)
    p.setFillColor(COLOR_SLATE_100)
    p.rect(40, y - box_h, width - 80, box_h, fill=1, stroke=1)
    
    # Label
    p.setFont("Helvetica-Bold", 8)
    p.setFillColor(COLOR_SLATE_600)
    p.drawString(60, y - 20, "NEURAL INTERPRETATION")
    
    # Prediction Value (Dynamic Font Size)
    prediction_text = str(prediction_data.get('prediction', 'N/A')).upper()
    font_size = 16
    if len(prediction_text) > 30:
        font_size = 11
    elif len(prediction_text) > 20:
        font_size = 13
        
    p.setFont("Helvetica-Bold", font_size)
    p.setFillColor(COLOR_MEDICAL_DARK if is_normal else HexColor('#991B1B'))
    p.drawString(60, y - 45, prediction_text)
    
    # Confidence (Now on its own line at the bottom)
    conf = prediction_data.get('confidence', 0)
    p.setFont("Helvetica-Bold", 9)
    p.setFillColor(COLOR_SLATE_600)
    p.drawString(60, y - 70, f"CONFIDENCE INDEX: {conf * 100:.2f}%")
    
    y -= box_h + 20

    # ── Informatics Distribution ──────────────────────────────────────────────────
    breakdown = prediction_data.get('breakdown', [])
    if breakdown:
        section_title("Statistical Distribution")
        
        bar_w = 300
        bar_h = 4
        
        for item in breakdown:
            label = str(item.get('label', '')).upper()
            pct = float(item.get('percentage', 0))
            
            p.setFont("Helvetica-Bold", 8)
            p.setFillColor(COLOR_MEDICAL_DARK)
            p.drawString(40, y, label)
            
            p.setFont("Helvetica", 8)
            p.drawRightString(width - 40, y, f"{pct:.1f}%")
            
            y -= 8
            # Bar Track
            p.setFillColor(COLOR_SLATE_100)
            p.rect(40, y, width - 80, bar_h, fill=1, stroke=0)
            
            # Bar Fill
            p.setFillColor(COLOR_TAN if 'normal' in label.lower() else COLOR_MEDICAL_DARK)
            p.rect(40, y, (width - 80) * (pct/100), bar_h, fill=1, stroke=0)
            
            y -= 20
            
            if y < 100:
                p.showPage()
                y = height - 60

    # ── Final Validation ─────────────────────────────────────────────────────────
    y = 120
    p.setStrokeColor(COLOR_SLATE_100)
    p.line(40, y, width - 40, y)
    
    p.setFont("Helvetica", 8)
    p.setFillColor(COLOR_SLATE_400)
    p.drawCentredString(cx, y - 15, "AUTHENTICATED BY HEARTSYNC CLOUD INFERENCE ENGINE")
    
    # ── Disclaimer Footer ────────────────────────────────────────────────────────
    p.setFillColor(COLOR_SLATE_100)
    p.rect(0, 0, width, 60, stroke=0, fill=1)
    
    p.setFont("Helvetica-Bold", 8)
    p.setFillColor(COLOR_SLATE_600)
    p.drawCentredString(cx, 35, "LEGAL DISCLAIMER")
    
    p.setFont("Helvetica", 7)
    p.setFillColor(COLOR_SLATE_400)
    p.drawCentredString(cx, 22, "This report is generated using advanced neural networks and is intended for clinical assistance only.")
    p.drawCentredString(cx, 12, "Consult with a board-certified cardiologist for definitive medical intervention.")

    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer
