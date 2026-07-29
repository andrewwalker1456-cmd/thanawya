"""
Thanaweya Amma Bot — Data Models
Lightweight data structures for student records.
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


class StudentRecord:
    """Represents a single student record. Optimized with slots for minimal memory footprint."""
    __slots__ = (
        "seat_number",
        "name",
        "grade",
        "student_case",
        "student_case_desc",
        "c_flag",
        "extra_fields",
    )

    def __init__(
        self,
        seat_number: int,
        name: str,
        grade: float,
        student_case: int,
        student_case_desc: str,
        c_flag: int,
        extra_fields: Dict[str, Any] = None,
    ):
        self.seat_number = seat_number
        self.name = name
        self.grade = grade
        self.student_case = student_case
        self.student_case_desc = student_case_desc
        self.c_flag = c_flag
        self.extra_fields = extra_fields if extra_fields is not None else {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for PDF generation."""
        d = {
            "رقم الجلوس": self.seat_number,
            "الاسم": self.name,
            "الدرجة": self.grade,
            "student_case": self.student_case,
            "student_case_desc": self.student_case_desc,
            "c_flage": self.c_flag,
        }
        d.update(self.extra_fields)
        return d

    @classmethod
    def from_row(cls, row_data: Dict[str, Any]) -> "StudentRecord":
        """Create a StudentRecord from a row dictionary with flexible column detection."""
        seat_number = cls._extract_seat_number(row_data)
        name = cls._extract_name(row_data)
        grade = cls._extract_grade(row_data)
        student_case = cls._extract_field(row_data, ["student_case", "حالة الطالب"], 0)
        student_case_desc = cls._extract_field_str(
            row_data, ["student_case_desc", "وصف الحالة"], ""
        )
        c_flag = cls._extract_field(row_data, ["c_flage", "c_flag", "العلامة"], 0)

        # Collect any extra fields not in the known set
        known_keys = {
            "رقم الجلوس", "الاسم", "الدرجة", "student_case",
            "student_case_desc", "c_flage", "c_flag", "حالة الطالب",
            "وصف الحالة", "العلامة",
        }
        extra = {k: v for k, v in row_data.items() if k not in known_keys}

        return cls(
            seat_number=seat_number,
            name=name,
            grade=grade,
            student_case=student_case,
            student_case_desc=student_case_desc,
            c_flag=c_flag,
            extra_fields=extra,
        )

    @staticmethod
    def _extract_seat_number(row: Dict[str, Any]) -> int:
        for key in ["رقم الجلوس", "seat_number", "Seat Number", "جلوس"]:
            if key in row:
                val = row[key]
                if val is not None:
                    return int(float(val))
        raise ValueError(f"Cannot find seat number column. Available: {list(row.keys())}")

    @staticmethod
    def _extract_name(row: Dict[str, Any]) -> str:
        for key in ["الاسم", "name", "Name", "الاسم بالكامل"]:
            if key in row:
                val = row[key]
                return str(val).strip() if val is not None else ""
        raise ValueError(f"Cannot find name column. Available: {list(row.keys())}")

    @staticmethod
    def _extract_grade(row: Dict[str, Any]) -> float:
        for key in ["الدرجة", "grade", "Grade", "المجموع", "الدرجة الكلية"]:
            if key in row:
                val = row[key]
                if val is not None:
                    return float(val)
        return 0.0

    @staticmethod
    def _extract_field(row: Dict[str, Any], keys: List[str], default=0):
        for key in keys:
            if key in row and row[key] is not None:
                try:
                    return int(row[key])
                except (ValueError, TypeError):
                    return default
        return default

    @staticmethod
    def _extract_field_str(row: Dict[str, Any], keys: List[str], default=""):
        for key in keys:
            if key in row and row[key] is not None:
                return str(row[key]).strip()
        return default


@dataclass
class ImportStats:
    """Statistics about a data import."""
    total_rows: int = 0
    valid_rows: int = 0
    duplicate_seats: int = 0
    import_time_seconds: float = 0.0
    file_path: str = ""
    columns: List[str] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class SearchStats:
    """Runtime search statistics."""
    total_searches: int = 0
    seat_searches: int = 0
    name_searches: int = 0
    today_searches: int = 0
    most_searched_seats: List[tuple] = field(default_factory=list)  # [(seat, count)]
    most_searched_names: List[tuple] = field(default_factory=list)  # [(name, count)]
    avg_search_time_ms: float = 0.0