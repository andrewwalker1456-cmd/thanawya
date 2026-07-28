"""
Thanaweya Amma Bot — PDF Generator
Generates professional PDFs with proper Arabic RTL text support.
Uses arabic_reshaper + python-bidi for correct Arabic rendering.
"""

import io
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

import arabic_reshaper
from bidi.algorithm import get_display

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm, cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Spacer, Paragraph, HRFlowable,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_CENTER, TA_RIGHT

from .models import StudentRecord

logger = logging.getLogger(__name__)

CASE_DESCRIPTIONS = {
    1: "ناجح دور أول",
    2: "دور ثان",
    3: "راسب دور أول",
    12: "غياب كلى دور أول",
}


def arabic(text: str) -> str:
    """Reshape and reorder Arabic text for correct PDF rendering."""
    if not text:
        return text
    reshaped = arabic_reshaper.reshape(text)
    return get_display(reshaped)


class PDFGenerator:
    """Generates professional PDF reports for student results with proper Arabic RTL."""

    def __init__(self, font_path: str, fallback_font_path: str):
        self.font_path = font_path
        self.fallback_font_path = fallback_font_path
        self._fonts_registered = False
        self._font_name = "ArabicFont"
        self._font_name_bold = "ArabicFontBold"

    def _register_fonts(self) -> bool:
        if self._fonts_registered:
            return True
        try:
            font_file = Path(self.font_path)
            if not font_file.exists():
                logger.warning(f"Font not found: {font_file}, using fallback")
                font_file = Path(self.fallback_font_path)
            pdfmetrics.registerFont(TTFont(self._font_name, str(font_file)))
            pdfmetrics.registerFont(TTFont(self._font_name_bold, str(font_file)))
            pdfmetrics.registerFontFamily(
                self._font_name, normal=self._font_name, bold=self._font_name_bold,
            )
            self._fonts_registered = True
            logger.info(f"Registered Arabic font: {font_file}")
            return True
        except Exception as e:
            logger.error(f"Font registration failed: {e}")
            return False

    def generate_pdf(self, record: StudentRecord) -> Optional[bytes]:
        """Generate a PDF for a student record. Returns PDF bytes or None."""
        if not self._register_fonts():
            logger.error("Cannot generate PDF — font registration failed")
            return None

        try:
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(
                buffer, pagesize=A4,
                rightMargin=2*cm, leftMargin=2*cm,
                topMargin=2*cm, bottomMargin=2*cm,
            )

            styles = getSampleStyleSheet()

            title_style = ParagraphStyle(
                "ArabicTitle", parent=styles["Title"],
                fontName=self._font_name_bold, fontSize=20,
                alignment=TA_CENTER, spaceAfter=4*mm,
                textColor=colors.HexColor("#1a5276"),
            )

            label_style = ParagraphStyle(
                "ArabicLabel", parent=styles["Normal"],
                fontName=self._font_name, fontSize=12,
                alignment=TA_RIGHT, leading=8*mm,
                textColor=colors.HexColor("#7f8c8d"),
            )

            value_style = ParagraphStyle(
                "ArabicValue", parent=styles["Normal"],
                fontName=self._font_name_bold, fontSize=13,
                alignment=TA_RIGHT, leading=8*mm,
                textColor=colors.HexColor("#2c3e50"),
            )

            footer_style = ParagraphStyle(
                "Footer", parent=styles["Normal"],
                fontName=self._font_name, fontSize=8,
                alignment=TA_CENTER,
                textColor=colors.HexColor("#aab7b8"),
            )

            elements = []

            # Header — Arabic title only
            elements.append(Paragraph(arabic("نتيجة الثانوية العامة"), title_style))
            elements.append(HRFlowable(
                width="80%", thickness=1, color=colors.HexColor("#2980b9"),
                spaceAfter=5*mm, spaceBefore=2*mm,
            ))

            # Data table
            data = record.to_dict()
            fields = self._get_ordered_fields(data)

            table_data = []
            for label_ar, value in fields:
                display_label = arabic(str(label_ar))
                display_value = arabic(self._format_value(label_ar, value))
                table_data.append([
                    Paragraph(display_value, value_style),
                    Paragraph(display_label, label_style),
                ])

            col_widths = [doc.width * 0.55, doc.width * 0.45]
            table = Table(table_data, colWidths=col_widths)
            table.setStyle(TableStyle([
                ("ROWBACKGROUNDS", (0,0), (-1,-1), [
                    colors.HexColor("#ffffff"), colors.HexColor("#f4f6f7"),
                ]),
                ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
                ("TOPPADDING", (0,0), (-1,-1), 4*mm),
                ("BOTTOMPADDING", (0,0), (-1,-1), 4*mm),
                ("LEFTPADDING", (0,0), (-1,-1), 3*mm),
                ("RIGHTPADDING", (0,0), (-1,-1), 3*mm),
                ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#d5dbdb")),
                ("LINEBELOW", (0,-1), (-1,-1), 1.5, colors.HexColor("#2980b9")),
            ]))
            elements.append(table)

            # Footer
            elements.append(Spacer(1, 8*mm))
            elements.append(HRFlowable(
                width="60%", thickness=0.5, color=colors.HexColor("#aab7b8"),
                spaceAfter=3*mm,
            ))
            elements.append(Paragraph(
                arabic("تم إنشاء هذا الملف تلقائياً — بوت نتيجة الثانوية"),
                footer_style,
            ))

            doc.build(elements)
            pdf_bytes = buffer.getvalue()
            buffer.close()
            return pdf_bytes

        except Exception as e:
            logger.error(f"PDF generation failed: {e}", exc_info=True)
            return None

    def _get_ordered_fields(self, data: Dict[str, Any]) -> List[tuple]:
        """Get display fields — includes core fields plus any extra subject scores."""
        fields = []

        if "الاسم" in data:
            fields.append(("الاسم", data["الاسم"]))
        if "رقم الجلوس" in data:
            fields.append(("رقم الجلوس", data["رقم الجلوس"]))
        if "الدرجة" in data:
            grade = data["الدرجة"]
            fields.append(("الدرجة", grade))
            if isinstance(grade, (int, float)):
                percentage = (grade / 320.0) * 100
                fields.append(("النسبة المئوية", f"{percentage:.2f}%"))
        if "student_case_desc" in data:
            fields.append(("الحالة", data["student_case_desc"]))
        elif "student_case" in data:
            case_val = data["student_case"]
            desc = CASE_DESCRIPTIONS.get(case_val, str(case_val))
            fields.append(("الحالة", desc))

        # Add extra fields (subject scores, etc.)
        skip_keys = {
            "الاسم", "رقم الجلوس", "الدرجة", "student_case",
            "student_case_desc", "c_flage",
        }
        for key, value in data.items():
            if key not in skip_keys and value is not None:
                fields.append((str(key), value))

        return fields

    def _format_value(self, label: str, value: Any) -> str:
        if label == "الدرجة" and isinstance(value, (int, float)):
            return f"{value:.2f} / 320"
        if isinstance(value, float):
            return f"{value:.2f}"
        if value is None:
            return "—"
        return str(value)

    def generate_filename(self, record: StudentRecord) -> str:
        seat = record.seat_number
        name = record.name.replace(" ", "_")[:50]
        safe_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in name)
        return f"{seat}_{safe_name}.pdf"
