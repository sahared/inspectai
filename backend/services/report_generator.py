import io
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

SEVERITY_COLORS = {
    "minor": (76, 175, 80),
    "moderate": (255, 152, 0),
    "severe": (244, 67, 54),
    "critical": (156, 39, 176),
}

class ReportGenerator:
    def __init__(self, storage_service):
        self.storage = storage_service

    async def generate(self, session_id, session_data, findings):
        try:
            pdf_bytes = self._build_pdf(session_id, session_data, findings)
            report_url = await self.storage.upload_report(session_id, pdf_bytes)
            logger.info(f"Report generated for session {session_id}")
            return report_url
        except Exception as e:
            logger.error(f"PDF generation failed: {e}")
            text = self._build_text_report(session_id, session_data, findings)
            return await self.storage.upload_file(text.encode(), f"sessions/{session_id}/reports/report.txt", "text/plain")

    def _build_pdf(self, session_id, session_data, findings):
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=60, leftMargin=60, topMargin=60, bottomMargin=60)
        styles = getSampleStyleSheet()
        story = []

        # Styles that WRAP text properly using Paragraph
        cell = ParagraphStyle("Cell", parent=styles["Normal"], fontSize=9, leading=12)
        cellb = ParagraphStyle("CellBold", parent=styles["Normal"], fontSize=9, leading=12, fontName="Helvetica-Bold")
        title = ParagraphStyle("Title2", parent=styles["Title"], fontSize=24, spaceAfter=6, textColor=colors.HexColor("#1A56DB"))
        heading = ParagraphStyle("Head", parent=styles["Heading2"], fontSize=14, spaceAfter=12, spaceBefore=20, textColor=colors.HexColor("#1A56DB"))

        # Header
        story.append(Paragraph("InspectAI", title))
        story.append(Paragraph("Property Damage Inspection Report", styles["Heading2"]))
        story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#1A56DB"), spaceAfter=20))

        # Metadata
        created = session_data.get("created_at", datetime.utcnow().isoformat())
        for label, val in [
            ("Report ID", session_id[:8].upper()),
            ("Claim Type", session_data.get("claim_type", "Property Damage").replace("_", " ").title()),
            ("Inspection Date", created[:10]),
            ("Total Findings", str(len(findings))),
            ("Generated", datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")),
        ]:
            story.append(Paragraph(f"<b>{label}:</b> {val}", cell))
        story.append(Spacer(1, 16))

        # Summary
        story.append(Paragraph("Executive Summary", heading))
        sev_counts = {}
        for f in findings:
            s = f.get("severity", "unknown")
            sev_counts[s] = sev_counts.get(s, 0) + 1
        rooms = set(f.get("room", "Unknown") for f in findings)
        parts = [f"{c} {s}" for s, c in sev_counts.items()]
        story.append(Paragraph(
            f"This inspection identified <b>{len(findings)}</b> findings across "
            f"<b>{len(rooms)}</b> area(s). Severity: {', '.join(parts)}.",
            styles["Normal"]
        ))
        story.append(Spacer(1, 16))

        # Severity table
        if sev_counts:
            sev_data = [[Paragraph("<b>Severity</b>", cellb), Paragraph("<b>Count</b>", cellb)]]
            for s in ["critical", "severe", "moderate", "minor"]:
                if s in sev_counts:
                    sev_data.append([Paragraph(s.upper(), cell), Paragraph(str(sev_counts[s]), cell)])
            st = Table(sev_data, colWidths=[200, 100])
            st.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1A56DB")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ]))
            story.append(st)
            story.append(Spacer(1, 16))

        # Detailed Findings
        story.append(Paragraph("Detailed Findings", heading))

        for i, f in enumerate(findings):
            num = f.get("evidence_number", i + 1)
            room = f.get("room", "Unknown").replace("_", " ").title()
            dtype = f.get("damage_type", "Unknown").replace("_", " ").title()
            sev = f.get("severity", "unknown")
            desc = f.get("description", "No description")
            action = f.get("recommended_action", "")
            ts = f.get("timestamp", "")
            photo = f.get("photo_path", "")

            sev_color = SEVERITY_COLORS.get(sev, (128, 128, 128))
            sev_hex = "#{:02x}{:02x}{:02x}".format(*sev_color)

            story.append(Paragraph(
                f"<b>Evidence #{num}: {dtype} — {room}</b>",
                ParagraphStyle(f"fh{i}", parent=styles["Heading3"], fontSize=11, spaceBefore=14, spaceAfter=4)
            ))

            # Use Paragraph for EVERY cell so text wraps properly
            rows = [
                [Paragraph("<b>Severity</b>", cellb), Paragraph(sev.upper(), cell)],
                [Paragraph("<b>Location</b>", cellb), Paragraph(room, cell)],
                [Paragraph("<b>Type</b>", cellb), Paragraph(dtype, cell)],
                [Paragraph("<b>Description</b>", cellb), Paragraph(desc, cell)],
            ]
            if action:
                rows.append([Paragraph("<b>Action</b>", cellb), Paragraph(action, cell)])
            if ts:
                rows.append([Paragraph("<b>Documented</b>", cellb), Paragraph(ts[:19], cell)])

            t = Table(rows, colWidths=[90, 400])
            t.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("BACKGROUND", (1, 0), (1, 0), colors.HexColor(sev_hex)),
                ("TEXTCOLOR", (1, 0), (1, 0), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
                ("LINEBELOW", (0, 0), (-1, -2), 0.25, colors.HexColor("#eeeeee")),
            ]))
            story.append(t)

            # Include evidence photo if available
            if photo and os.path.exists(photo):
                try:
                    story.append(Spacer(1, 4))
                    story.append(Image(photo, width=3 * inch, height=2.25 * inch))
                    story.append(Paragraph(
                        f"<i>Photo evidence #{num}</i>",
                        ParagraphStyle("cap", parent=cell, fontSize=7, textColor=colors.grey, alignment=1)
                    ))
                except Exception as e:
                    logger.warning(f"Photo error: {e}")

            story.append(Spacer(1, 6))

        # Areas Inspected
        story.append(Paragraph("Areas Inspected", heading))
        story.append(Paragraph(
            ", ".join(r.replace("_", " ").title() for r in sorted(rooms)),
            styles["Normal"]
        ))
        story.append(Spacer(1, 20))

        # Disclaimer
        story.append(HRFlowable(width="100%", thickness=1, color=colors.grey, spaceAfter=12))
        story.append(Paragraph(
            "<b>Disclaimer:</b> This report was generated by InspectAI, an AI-powered inspection tool. "
            "It does not constitute a professional structural engineering assessment. "
            "For structural concerns, consult a licensed professional.",
            ParagraphStyle("disc", parent=styles["Normal"], fontSize=8, textColor=colors.grey)
        ))

        doc.build(story)
        buffer.seek(0)
        return buffer.read()

    def _build_text_report(self, session_id, session_data, findings):
        lines = ["=" * 60, "INSPECTAI INSPECTION REPORT", "=" * 60, f"ID: {session_id[:8]}", f"Findings: {len(findings)}", ""]
        for f in findings:
            lines.extend([
                f"#{f.get('evidence_number', '?')} [{f.get('severity', '?').upper()}] {f.get('damage_type', '?')} in {f.get('room', '?')}",
                f"  {f.get('description', 'N/A')}", ""
            ])
        return "\n".join(lines)
