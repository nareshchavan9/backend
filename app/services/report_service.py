from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, black, white
from io import BytesIO
from datetime import datetime

# Color palette for beat type bars (matches frontend)
BAR_COLORS = [
    HexColor('#2D3FE2'),  # healthcare-blue
    HexColor('#14B8A6'),  # teal-500
    HexColor('#FB923C'),  # orange-400
    HexColor('#A855F7'),  # purple-500
    HexColor('#F87171'),  # red-400
    HexColor('#F472B6'),  # pink-400
]


def generate_pdf_report(prediction_data: dict, user_data: dict, doctor_data: dict = None):
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    cx = width / 2  # horizontal center of page

    # ── Header ───────────────────────────────────────────────────────────────────
    p.setFillColor(HexColor('#1A1C20'))
    p.rect(0, height - 70, width, 70, stroke=0, fill=1)

    p.setFont("Helvetica-Bold", 20)
    p.setFillColor(white)
    p.drawCentredString(cx, height - 40, "Arrhythmia Detection Report")

    p.setFont("Helvetica", 9)
    p.setFillColor(HexColor('#94A3B8'))
    p.drawCentredString(cx, height - 58, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    y = height - 100

    # ── Section heading helper ────────────────────────────────────────────────────
    def section_heading(title):
        nonlocal y
        y -= 6
        p.setFont("Helvetica-Bold", 11)
        p.setFillColor(HexColor('#2D3FE2'))
        p.drawCentredString(cx, y, title)
        y -= 4
        p.setStrokeColor(HexColor('#2D3FE2'))
        p.line(cx - 130, y, cx + 130, y)
        y -= 16

    # ── Patient Information ───────────────────────────────────────────────────────
    section_heading("PATIENT INFORMATION")

    fields = [
        ("Name",   user_data.get('name', 'N/A')),
        ("Email",  user_data.get('email', 'N/A')),
        ("Age",    str(user_data.get('age', 'N/A'))),
        ("Gender", str(user_data.get('gender', 'N/A'))),
    ]
    for label, value in fields:
        p.setFont("Helvetica-Bold", 10)
        p.setFillColor(HexColor('#475569'))
        p.drawRightString(cx - 10, y, f"{label}:")
        p.setFont("Helvetica", 10)
        p.setFillColor(black)
        p.drawString(cx, y, value)
        y -= 17

    y -= 10

    # ── Diagnosis Results ─────────────────────────────────────────────────────────
    section_heading("DIAGNOSIS RESULTS")

    is_normal  = str(prediction_data.get('prediction', '')).lower() == 'normal'
    box_color  = HexColor('#DCFCE7') if is_normal else HexColor('#FEE2E2')
    text_color = HexColor('#16A34A') if is_normal else HexColor('#DC2626')

    box_w, box_h = 360, 68
    p.setFillColor(box_color)
    p.roundRect(cx - box_w / 2, y - box_h + 12, box_w, box_h, 8, stroke=0, fill=1)

    p.setFont("Helvetica-Bold", 14)
    p.setFillColor(text_color)
    p.drawCentredString(cx, y - 8, f"Classification: {prediction_data.get('prediction', 'N/A')}")

    conf = prediction_data.get('confidence', 0)
    p.setFont("Helvetica", 11)
    p.setFillColor(HexColor('#334155'))
    p.drawCentredString(cx, y - 24, f"Confidence Score: {conf * 100:.2f}%")

    # Timestamp
    timestamp = prediction_data.get('timestamp')
    date_str, time_str = 'N/A', 'N/A'
    if isinstance(timestamp, datetime):
        date_str = timestamp.strftime('%Y-%m-%d')
        time_str = timestamp.strftime('%H:%M:%S')
    elif timestamp:
        ts_str = str(timestamp)
        for sep in (' ', 'T'):
            if sep in ts_str:
                date_str, time_str = ts_str.split(sep, 1)
                break
        else:
            date_str = ts_str

    p.setFont("Helvetica", 9)
    p.setFillColor(HexColor('#64748B'))
    p.drawCentredString(cx, y - 42, f"Date: {date_str}   |   Time: {time_str}")

    y -= box_h + 18

    # ── Beat Type Distribution ────────────────────────────────────────────────────
    breakdown = prediction_data.get('breakdown', [])
    if breakdown:
        section_heading("BEAT TYPE DISTRIBUTION")

        bar_total_w = 340
        bar_h       = 13
        label_w     = 110
        pct_w       = 44
        track_w     = bar_total_w - label_w - pct_w - 12
        bar_left    = cx - bar_total_w / 2

        for idx, item in enumerate(breakdown):
            label_text = str(item.get('label', ''))
            is_normal = 'normal' in label_text.lower()
            
            # Define colors for PDF
            GREEN = HexColor('#16A34A')
            RED_DARK = HexColor('#DC2626')
            ORANGE = HexColor('#F97316')
            RED_LIGHT = HexColor('#F87171')
            GRAY = HexColor('#94A3B8')

            if is_normal:
                color = GREEN
            elif idx == 0:
                color = RED_DARK
            elif idx == 1:
                color = ORANGE
            elif idx == 2:
                color = RED_LIGHT
            else:
                color = GRAY

            pct    = min(float(item.get('percentage', 0)), 100)
            fill_w = track_w * pct / 100

            if len(label_text) > 16:
                label_text = label_text[:15] + '…'

            # Label (right-aligned)
            p.setFont("Helvetica", 9)
            p.setFillColor(HexColor('#334155'))
            p.drawRightString(bar_left + label_w, y + 2, label_text)

            track_x = bar_left + label_w + 6

            # Background track
            p.setFillColor(HexColor('#E2E8F0'))
            p.roundRect(track_x, y, track_w, bar_h, 4, stroke=0, fill=1)

            # Filled portion
            if fill_w > 0:
                p.setFillColor(color)
                p.roundRect(track_x, y, fill_w, bar_h, 4, stroke=0, fill=1)

            # Percentage label
            p.setFont("Helvetica-Bold", 9)
            p.setFillColor(color)
            p.drawString(track_x + track_w + 6, y + 2, f"{pct:.1f}%")

            y -= bar_h + 8

            if y < 110:
                p.showPage()
                y = height - 60

        y -= 6

    # ── Medical Professional ──────────────────────────────────────────────────────
    section_heading("MEDICAL PROFESSIONAL" if doctor_data else "ASSESSMENT MODE")

    p.setFont("Helvetica", 10)
    p.setFillColor(black)
    if doctor_data:
        for line in [
            f"Practitioner: Dr. {doctor_data.get('name', 'N/A')}",
            f"Email: {doctor_data.get('email', 'N/A')}",
            f"Role: {str(doctor_data.get('role', '')).capitalize()}",
        ]:
            p.drawCentredString(cx, y, line)
            y -= 16
    else:
        p.drawCentredString(cx, y, "Mode: Patient Self-Assessment")

    # ── Disclaimer footer ─────────────────────────────────────────────────────────
    p.setFillColor(HexColor('#F1F5F9'))
    p.rect(0, 0, width, 70, stroke=0, fill=1)

    p.setFont("Helvetica-Bold", 9)
    p.setFillColor(HexColor('#475569'))
    p.drawCentredString(cx, 52, "Disclaimer")

    p.setFont("Helvetica-Oblique", 8)
    p.setFillColor(HexColor('#64748B'))
    p.drawCentredString(cx, 37, "This is an AI-generated report for informational purposes only.")
    p.drawCentredString(cx, 23, "Please consult a qualified medical professional for a definitive diagnosis.")

    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer
