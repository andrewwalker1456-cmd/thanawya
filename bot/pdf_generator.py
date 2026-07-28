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
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

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
                rightMargin=1.5*cm, leftMargin=1.5*cm,
                topMargin=1.5*cm, bottomMargin=1.5*cm,
            )

            styles = getSampleStyleSheet()

            # Define modern premium colors
            c_primary = colors.HexColor("#1E3A8A")   # Deep Royal Blue
            c_slate_dark = colors.HexColor("#0F172A") # Slate-900
            c_slate_gray = colors.HexColor("#475569") # Slate-600
            c_slate_light = colors.HexColor("#94A3B8") # Slate-400
            c_bg_light = colors.HexColor("#F8FAFC")    # Slate-50
            c_border = colors.HexColor("#E2E8F0")      # Slate-200

            title_style = ParagraphStyle(
                "ArabicTitle", parent=styles["Title"],
                fontName=self._font_name_bold, fontSize=18,
                alignment=TA_CENTER, spaceAfter=2*mm,
                textColor=c_slate_dark,
            )

            subtitle_style = ParagraphStyle(
                "ArabicSubTitle", parent=styles["Normal"],
                fontName=self._font_name, fontSize=9,
                alignment=TA_CENTER, spaceAfter=6*mm,
                textColor=c_slate_gray,
            )

            card_label_style = ParagraphStyle(
                "CardLabel", parent=styles["Normal"],
                fontName=self._font_name, fontSize=11,
                alignment=TA_RIGHT, textColor=c_slate_gray,
            )

            card_value_style = ParagraphStyle(
                "CardValue", parent=styles["Normal"],
                fontName=self._font_name_bold, fontSize=11,
                alignment=TA_RIGHT, textColor=c_slate_dark,
            )

            section_title_style = ParagraphStyle(
                "SectionTitle", parent=styles["Heading2"],
                fontName=self._font_name_bold, fontSize=13,
                alignment=TA_RIGHT, spaceBefore=6*mm, spaceAfter=3*mm,
                textColor=c_primary,
            )

            th_label_style = ParagraphStyle(
                "ThLabel", parent=styles["Normal"],
                fontName=self._font_name_bold, fontSize=11,
                alignment=TA_RIGHT, textColor=colors.white,
            )

            td_label_style = ParagraphStyle(
                "TdLabel", parent=styles["Normal"],
                fontName=self._font_name, fontSize=10,
                alignment=TA_RIGHT, textColor=colors.HexColor("#334155"),
            )

            td_value_style = ParagraphStyle(
                "TdValue", parent=styles["Normal"],
                fontName=self._font_name_bold, fontSize=10,
                alignment=TA_RIGHT, textColor=c_slate_dark,
            )

            footer_style = ParagraphStyle(
                "Footer", parent=styles["Normal"],
                fontName=self._font_name, fontSize=8,
                alignment=TA_CENTER,
                textColor=c_slate_light,
            )

            elements = []

            # 1. TOP BAR DECORATION
            elements.append(HRFlowable(
                width="100%", thickness=4, color=c_primary,
                spaceAfter=5*mm, spaceBefore=0,
            ))

            # 2. MINISTRY HEADER TEXT
            header_right_style = ParagraphStyle(
                "HeaderRight", parent=styles["Normal"],
                fontName=self._font_name, fontSize=9,
                alignment=TA_RIGHT, textColor=c_slate_gray,
                leading=12,
            )
            header_left_style = ParagraphStyle(
                "HeaderLeft", parent=styles["Normal"],
                fontName=self._font_name, fontSize=9,
                alignment=TA_LEFT, textColor=c_slate_gray,
                leading=12,
            )
            
            header_table_data = [
                [
                    Paragraph(arabic("جمهورية مصر العربية\nوزارة التربية والتعليم والتعليم الفني\nإدارة نظم المعلومات"), header_right_style),
                    Paragraph(arabic("امتحان شهادة إتمام الدراسة\nالثانوية العامة المصرية\nالعام الدراسي: ٢٠٢٥ / ٢٠٢٦"), header_left_style)
                ]
            ]
            header_table = Table(header_table_data, colWidths=[doc.width * 0.5, doc.width * 0.5])
            header_table.setStyle(TableStyle([
                ("VALIGN", (0,0), (-1,-1), "TOP"),
                ("LEFTPADDING", (0,0), (-1,-1), 0),
                ("RIGHTPADDING", (0,0), (-1,-1), 0),
                ("BOTTOMPADDING", (0,0), (-1,-1), 2*mm),
            ]))
            elements.append(header_table)

            # 3. TITLE
            elements.append(Paragraph(arabic("إخطار رسمي بنتيجة الطالب"), title_style))
            elements.append(Paragraph(arabic("امتحانات الدور الأول للثانوية العامة"), subtitle_style))

            # 4. EXTRACT CORE AND DYNAMIC DATA
            data = record.to_dict()
            student_name = data.get("الاسم", "—")
            seat_num = data.get("رقم الجلوس", "—")
            grade = data.get("الدرجة", 0.0) or 0.0
            status_desc = data.get("student_case_desc", "—")
            if status_desc == "—" and "student_case" in data:
                status_desc = CASE_DESCRIPTIONS.get(data["student_case"], str(data["student_case"]))
            
            percentage = (grade / 320.0) * 100 if isinstance(grade, (int, float)) else 0.0
            
            # Dynamic lookup for branch, school, administration
            branch = "—"
            for k in ["الشعبة", "الشعبه", "التخصص", "شعبة"]:
                if k in data:
                    branch = data[k]
                    break

            school = "—"
            for k in ["المدرسة", "المدرسه", "اسم المدرسة", "اسم المدرسه"]:
                if k in data:
                    school = data[k]
                    break

            admin_dept = "—"
            for k in ["الإدارة", "الادارة", "الاداره", "الإدارة التعليمية", "الادارة التعليمية"]:
                if k in data:
                    admin_dept = data[k]
                    break

            # Determine status badge text color
            status_color = "#10B981"  # Emerald Green for Passed
            if any(x in status_desc for x in ["راسب", "دور ثان", "غياب"]):
                status_color = "#EF4444"  # Red for fail/warning

            card_status_style = ParagraphStyle(
                "CardStatus", parent=styles["Normal"],
                fontName=self._font_name_bold, fontSize=11,
                alignment=TA_RIGHT, textColor=colors.HexColor(status_color),
            )

            disp_name = arabic(str(student_name))
            disp_school = arabic(str(school))
            disp_seat = arabic(str(seat_num))
            disp_branch = arabic(str(branch))
            disp_admin = arabic(str(admin_dept))
            disp_grade = arabic(f"{grade:.2f}")
            disp_pct = arabic(f"{percentage:.2f}%")
            disp_status = arabic(status_desc)

            # 5. SUMMARY CARD
            card_data = [
                # Row 0: Name (spanned) & Label
                [
                    Paragraph(disp_name, card_value_style),
                    Paragraph(arabic(""), card_label_style),
                    Paragraph(arabic(""), card_label_style),
                    Paragraph(arabic("اسم الطالب:"), card_label_style),
                ],
                # Row 1: School (spanned) & Label
                [
                    Paragraph(disp_school, card_value_style),
                    Paragraph(arabic(""), card_label_style),
                    Paragraph(arabic(""), card_label_style),
                    Paragraph(arabic("المدرسة:"), card_label_style),
                ],
                # Row 2: Seat & Branch
                [
                    Paragraph(disp_seat, card_value_style),
                    Paragraph(arabic("رقم الجلوس:"), card_label_style),
                    Paragraph(disp_branch, card_value_style),
                    Paragraph(arabic("الشعبة:"), card_label_style),
                ],
                # Row 3: Status & Admin Dept
                [
                    Paragraph(disp_status, card_status_style),
                    Paragraph(arabic("حالة الطالب:"), card_label_style),
                    Paragraph(disp_admin, card_value_style),
                    Paragraph(arabic("الإدارة التعليمية:"), card_label_style),
                ],
                # Row 4: Grade & Percentage
                [
                    Paragraph(disp_grade, card_value_style),
                    Paragraph(arabic("المجموع الكلي:"), card_label_style),
                    Paragraph(disp_pct, card_value_style),
                    Paragraph(arabic("النسبة المئوية:"), card_label_style),
                ]
            ]

            card_width = doc.width
            col_w = [card_width * 0.35, card_width * 0.15, card_width * 0.35, card_width * 0.15]
            
            card_table = Table(card_data, colWidths=col_w)
            card_table.setStyle(TableStyle([
                ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
                ("TOPPADDING", (0,0), (-1,-1), 2.5*mm),
                ("BOTTOMPADDING", (0,0), (-1,-1), 2.5*mm),
                ("LEFTPADDING", (0,0), (-1,-1), 3*mm),
                ("RIGHTPADDING", (0,0), (-1,-1), 3*mm),
                ("BACKGROUND", (0,0), (-1,-1), c_bg_light),
                ("GRID", (0,0), (-1,-1), 1, c_border),
                # Spans for Name and School
                ("SPAN", (0,0), (2,0)),
                ("SPAN", (0,1), (2,1)),
            ]))
            elements.append(card_table)

            # 6. DETAILED SUBJECT GRADES
            skip_keys = {
                "الاسم", "رقم الجلوس", "الدرجة", "student_case",
                "student_case_desc", "c_flage", "النسبة المئوية",
                "الشعبة", "الشعبه", "التخصص", "شعبة",
                "المدرسة", "المدرسه", "اسم المدرسة", "اسم المدرسه",
                "الإدارة", "الادارة", "الاداره", "الإدارة التعليمية", "الادارة التعليمية"
            }
            subject_fields = []
            for key, value in data.items():
                if key not in skip_keys and value is not None:
                    subject_fields.append((str(key), value))

            if subject_fields:
                elements.append(Paragraph(arabic("بيان درجات المواد الدراسية تفصيلاً"), section_title_style))

                table_data = [[
                    Paragraph(arabic("الدرجة الحاصل عليها"), th_label_style),
                    Paragraph(arabic("اسم المادة الدراسية"), th_label_style),
                ]]

                for label_ar, value in subject_fields:
                    display_label = arabic(str(label_ar))
                    display_value = arabic(self._format_value(label_ar, value))
                    table_data.append([
                        Paragraph(display_value, td_value_style),
                        Paragraph(display_label, td_label_style),
                    ])

                col_widths = [doc.width * 0.45, doc.width * 0.55]
                table = Table(table_data, colWidths=col_widths)
                table.setStyle(TableStyle([
                    ("BACKGROUND", (0,0), (-1,0), c_primary),
                    ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
                    ("TOPPADDING", (0,0), (-1,-1), 2.5*mm),
                    ("BOTTOMPADDING", (0,0), (-1,-1), 2.5*mm),
                    ("LEFTPADDING", (0,0), (-1,-1), 3*mm),
                    ("RIGHTPADDING", (0,0), (-1,-1), 3*mm),
                    ("GRID", (0,0), (-1,-1), 0.5, c_border),
                    ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, c_bg_light]),
                ]))
                elements.append(table)

            # 7. FOOTER SECTION
            elements.append(Spacer(1, 10*mm))
            elements.append(HRFlowable(
                width="80%", thickness=0.5, color=c_slate_light,
                spaceAfter=4*mm,
            ))
            elements.append(Paragraph(
                arabic("هذا المستند يعتبر إخطاراً رسمياً بالنتيجة ومستخرج تلقائياً من قاعدة بيانات وزارة التربية والتعليم"),
                footer_style,
            ))

            doc.build(elements)
            pdf_bytes = buffer.getvalue()
            buffer.close()
            return pdf_bytes

        except Exception as e:
            logger.error(f"PDF generation failed: {e}", exc_info=True)
            return None

    def _format_value(self, label: str, value: Any) -> str:
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
