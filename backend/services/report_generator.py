"""
Report Generator
Creates professional PDF inspection reports from findings.
"""

import io
import logging
from datetime import datetime
from typing import List

logger = logging.getLogger(__name__)

# Severity color mapping
SEVERITY_COLORS = {
    "minor": (76, 175, 80),       # Green
    "moderate": (255, 152, 0),     # Orange
    "severe": (244, 67, 54),       # Red
    "critical": (156, 39, 176),    # Purple
}


class ReportGenerator:
    """Generates professional PDF inspection reports."""

    def __init__(self, storage_service):
        self.storage = storage_service

    async def generate(
        self,
        session_id: str,
        session_data: dict,
        findings: list,
    ) -> str:
        """
        Generate a PDF report and upload to Cloud Storage.
        Returns the report URL.
        """
        try:
            pdf_bytes = self._build_pdf(session_id, session_data, findings)
            report_url = await self.storage.upload_report(session_id, pdf_bytes)
            logger.info(f"Report generated for session {session_id}: {report_url}")
            return report_url
        except ImportError:
            # If reportlab not available, generate a simple text report
            logger.warning("reportlab not available, generating text report")
            text_report = self._build_text_report(
                session_id, session_data, findings
            )
            report_url = await self.storage.upload_file(
                text_report.encode("utf-8"),
                f"sessions/{session_id}/reports/inspection_report.txt",
                "text/plain",
            )
            return report_url

    def _build_pdf(
        self,
        session_id: str,
        session_data: dict,
        findings: list,
    ) -> bytes:
        """Build the PDF report using reportlab."""
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
            HRFlowable, PageBreak
        )

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=72,
        )

        styles = getSampleStyleSheet()
        story = []

        # Custom styles
        title_style = ParagraphStyle(
            "CustomTitle",
            parent=styles["Title"],
            fontSize=24,
            spaceAfter=6,
            textColor=colors.HexColor("#1A56DB"),
        )
        heading_style = ParagraphStyle(
            "CustomHeading",
            parent=styles["Heading2"],
            fontSize=14,
            spaceAfter=12,
            spaceBefore=20,
            textColor=colors.HexColor("#1A56DB"),
        )
        body_style = styles["Normal"]

        # =====================================================================
        # HEADER
        # =====================================================================
        story.append(Paragraph("InspectAI", title_style))
        story.append(Paragraph("Property Damage Inspection Report", styles["Heading2"]))
        story.append(HRFlowable(
            width="100%", thickness=2,
            color=colors.HexColor("#1A56DB"), spaceAfter=20
        ))

        # Report metadata
        claim_type = session_data.get("claim_type", "Property Damage")
        created = session_data.get("created_at", datetime.utcnow().isoformat())
        meta_data = [
            ["Report ID:", session_id[:8].upper()],
            ["Claim Type:", claim_type.replace("_", " ").title()],
            ["Inspection Date:", created[:10]],
            ["Total Findings:", str(len(findings))],
            ["Generated:", datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")],
        ]
        meta_table = Table(meta_data, colWidths=[120, 350])
        meta_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 20))

        # =====================================================================
        # EXECUTIVE SUMMARY
        # =====================================================================
        story.append(Paragraph("Executive Summary", heading_style))

        # Severity breakdown
        severity_counts = {}
        for f in findings:
            sev = f.get("severity", "unknown")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        summary_text = (
            f"This inspection identified {len(findings)} findings across "
            f"{len(set(f.get('room', '') for f in findings))} areas. "
        )
        if severity_counts:
            parts = [f"{count} {sev}" for sev, count in severity_counts.items()]
            summary_text += f"Severity breakdown: {', '.join(parts)}."

        story.append(Paragraph(summary_text, body_style))
        story.append(Spacer(1, 12))

        # Severity summary table
        if severity_counts:
            sev_data = [["Severity", "Count"]]
            for sev in ["critical", "severe", "moderate", "minor"]:
                if sev in severity_counts:
                    sev_data.append([sev.upper(), str(severity_counts[sev])])

            sev_table = Table(sev_data, colWidths=[200, 100])
            sev_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1A56DB")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ]))
            story.append(sev_table)
            story.append(Spacer(1, 20))

        # =====================================================================
        # DETAILED FINDINGS
        # =====================================================================
        story.append(Paragraph("Detailed Findings", heading_style))

        for i, finding in enumerate(findings):
            # Finding header
            evidence_num = finding.get("evidence_number", i + 1)
            room = finding.get("room", "Unknown").replace("_", " ").title()
            damage_type = finding.get("damage_type", "Unknown").replace("_", " ").title()
            severity = finding.get("severity", "unknown").upper()

            story.append(Paragraph(
                f"<b>Evidence #{evidence_num}: {damage_type} — {room}</b>",
                ParagraphStyle(
                    f"finding_{i}",
                    parent=styles["Heading3"],
                    fontSize=12,
                    spaceBefore=16,
                    spaceAfter=4,
                )
            ))

            # Finding details table
            detail_data = [
                ["Severity:", severity],
                ["Location:", room],
                ["Type:", damage_type],
                ["Description:", finding.get("description", "No description")],
            ]
            if finding.get("recommended_action"):
                detail_data.append([
                    "Recommended Action:", finding["recommended_action"]
                ])
            if finding.get("timestamp"):
                detail_data.append(["Documented At:", finding["timestamp"][:19]])

            detail_table = Table(detail_data, colWidths=[130, 340])

            # Color-code severity
            sev_lower = finding.get("severity", "minor")
            sev_color = SEVERITY_COLORS.get(sev_lower, (128, 128, 128))
            sev_hex = "#{:02x}{:02x}{:02x}".format(*sev_color)

            detail_table.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("BACKGROUND", (1, 0), (1, 0), colors.HexColor(sev_hex)),
                ("TEXTCOLOR", (1, 0), (1, 0), colors.white),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            story.append(detail_table)
            story.append(Spacer(1, 8))

        # =====================================================================
        # AREAS INSPECTED
        # =====================================================================
        story.append(Paragraph("Areas Inspected", heading_style))
        areas = session_data.get("areas_inspected", [])
        if areas:
            areas_text = ", ".join(
                a.replace("_", " ").title() for a in sorted(areas)
            )
            story.append(Paragraph(areas_text, body_style))
        else:
            story.append(Paragraph("No areas recorded.", body_style))

        story.append(Spacer(1, 20))

        # =====================================================================
        # DISCLAIMER
        # =====================================================================
        story.append(HRFlowable(
            width="100%", thickness=1, color=colors.grey, spaceAfter=12
        ))
        disclaimer_style = ParagraphStyle(
            "Disclaimer",
            parent=body_style,
            fontSize=8,
            textColor=colors.grey,
        )
        story.append(Paragraph(
            "<b>Disclaimer:</b> This report was generated by InspectAI, an AI-powered "
            "inspection tool. It is intended to assist in the insurance claims process "
            "and does not constitute a professional structural engineering assessment. "
            "For structural concerns, please consult a licensed professional. "
            "Cost estimates are approximate and based on industry averages.",
            disclaimer_style,
        ))

        # Build PDF
        doc.build(story)
        buffer.seek(0)
        return buffer.read()

    def _build_text_report(
        self,
        session_id: str,
        session_data: dict,
        findings: list,
    ) -> str:
        """Fallback: generate a plain text report."""
        lines = [
            "=" * 60,
            "INSPECTAI — PROPERTY DAMAGE INSPECTION REPORT",
            "=" * 60,
            "",
            f"Report ID: {session_id[:8].upper()}",
            f"Claim Type: {session_data.get('claim_type', 'Property Damage')}",
            f"Date: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
            f"Total Findings: {len(findings)}",
            "",
            "-" * 60,
            "FINDINGS",
            "-" * 60,
        ]

        for f in findings:
            lines.extend([
                "",
                f"Evidence #{f.get('evidence_number', '?')}: "
                f"{f.get('damage_type', 'Unknown').replace('_', ' ').title()}",
                f"  Room: {f.get('room', 'Unknown').replace('_', ' ').title()}",
                f"  Severity: {f.get('severity', 'Unknown').upper()}",
                f"  Description: {f.get('description', 'N/A')}",
                f"  Recommended: {f.get('recommended_action', 'N/A')}",
            ])

        lines.extend([
            "",
            "-" * 60,
            "This report was generated by InspectAI.",
            "It does not constitute a professional engineering assessment.",
        ])

        return "\n".join(lines)
