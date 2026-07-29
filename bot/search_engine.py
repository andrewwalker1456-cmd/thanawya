import sqlite3
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional
from .arabic_normalizer import ArabicNormalizer
from .models import StudentRecord

logger = logging.getLogger(__name__)


class SearchEngine:
    """
    SQLite-backed, high-performance search engine.
    Queries the SQLite database directly on-demand to run in near 0MB memory.
    """

    def __init__(self, db_path: str, normalize_teh: bool = False):
        self.db_path = db_path
        self.normalizer = ArabicNormalizer(normalize_teh=normalize_teh)
        self._total_records = 0

    @property
    def total_records(self) -> int:
        if self._total_records == 0:
            try:
                conn = sqlite3.connect(self.db_path)
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM students")
                self._total_records = cur.fetchone()[0]
                conn.close()
            except Exception as e:
                logger.warning(f"Failed to fetch total records count: {e}")
        return self._total_records

    def load_records(self, records: List[StudentRecord]) -> int:
        """No-op for database-backed search engine."""
        return 0

    def load_indexes_direct(self, seat_index: dict, name_index: dict,
                                  name_tokens_index: dict, total: int) -> None:
        """No-op for database-backed search engine."""
        pass

    def dump_indexes(self) -> dict:
        """No-op for database-backed search engine."""
        return {}

    def get_stats(self) -> dict:
        """Return search engine statistics."""
        return {
            "total_records": self.total_records,
            "unique_names": self.total_records,
            "unique_tokens": 0,
        }

    def is_loaded(self) -> bool:
        """Check if database file exists and contains data."""
        return Path(self.db_path).exists()

    def search_by_seat(self, seat_number: int) -> Optional[StudentRecord]:
        """O(1) database lookup by seat number."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM students WHERE seating_no = ?", (seat_number,))
            row = cur.fetchone()
            if not row:
                return None

            # Fetch extra subject scores if available
            extra = {}
            try:
                cur.execute("SELECT * FROM student_subjects WHERE seating_no = ?", (seat_number,))
                sub_row = cur.fetchone()
                if sub_row:
                    for key in ["s1", "s10", "s14"]:
                        if key in sub_row.keys() and sub_row[key] is not None:
                            num = key[1:]
                            extra[f"المادة {num}"] = sub_row[key]
            except sqlite3.OperationalError:
                pass

            return StudentRecord(
                seat_number=int(row["seating_no"]),
                name=str(row["arabic_name"] or "").strip(),
                grade=float(row["total_degree"] or 0),
                student_case=int(row["student_case"] or 0),
                student_case_desc=str(row["student_case_desc"] or "").strip(),
                c_flag=int(row["c_flage"] or 0),
                extra_fields=extra,
            )
        except Exception as e:
            logger.error(f"DB search by seat failed: {e}")
            return None
        finally:
            conn.close()

    def search_by_name(self, name: str) -> List[StudentRecord]:
        """
        Database-backed search by Arabic name using high-performance wildcard queries.
        """
        words = name.strip().split()
        if not words:
            return []

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()

            clauses = []
            params = []
            for word in words:
                variations = {word}
                norm_word = self.normalizer.normalize(word)
                variations.add(norm_word)

                # Split fused prefixes (e.g. "عبدالرحمن")
                m = re.match(r"^(عبدال|ابوال|ابيل|أبوال|أبيل)(.*)$", word)
                if m:
                    prefix = m.group(1)
                    rest = m.group(2)
                    if prefix.startswith("عبد"):
                        variations.add(f"عبد%{rest}")
                        if rest.startswith("ال"):
                            variations.add(f"عبد%{rest[2:]}")

                word_clauses = []
                for v in variations:
                    pat = v
                    for a in ["أ", "إ", "آ", "ٱ", "ا"]:
                        pat = pat.replace(a, "_")
                    for y in ["ي", "ى"]:
                        pat = pat.replace(y, "_")
                    if pat.endswith("ة") or pat.endswith("ه"):
                        pat = pat[:-1] + "_"

                    if v.startswith("ال") and len(v) > 3:
                        word_clauses.append("arabic_name LIKE ?")
                        params.append(f"%{pat}%")
                        word_clauses.append("arabic_name LIKE ?")
                        params.append(f"%{pat[2:]}%")
                    else:
                        word_clauses.append("arabic_name LIKE ?")
                        params.append(f"%{pat}%")

                clauses.append(f"({' OR '.join(word_clauses)})")

            query = f"SELECT * FROM students WHERE {' AND '.join(clauses)} LIMIT 15"
            cur.execute(query, params)
            rows = cur.fetchall()

            # Build StudentRecord objects
            results = []
            for row in rows:
                seating_no = int(row["seating_no"])
                extra = {}
                try:
                    cur.execute("SELECT * FROM student_subjects WHERE seating_no = ?", (seating_no,))
                    sub_row = cur.fetchone()
                    if sub_row:
                        for key in ["s1", "s10", "s14"]:
                            if key in sub_row.keys() and sub_row[key] is not None:
                                num = key[1:]
                                extra[f"المادة {num}"] = sub_row[key]
                except sqlite3.OperationalError:
                    pass

                results.append(
                    StudentRecord(
                        seat_number=seating_no,
                        name=str(row["arabic_name"] or "").strip(),
                        grade=float(row["total_degree"] or 0),
                        student_case=int(row["student_case"] or 0),
                        student_case_desc=str(row["student_case_desc"] or "").strip(),
                        c_flag=int(row["c_flage"] or 0),
                        extra_fields=extra,
                    )
                )

            # Sort results by similarity score
            norm_search = self.normalizer.normalize_for_search(name)
            results.sort(key=lambda r: self._name_similarity_score(norm_search, r))
            return results[:10]

        except Exception as e:
            logger.error(f"DB search by name failed: {e}")
            return []
        finally:
            conn.close()

    def _name_similarity_score(self, norm_search: str, record: StudentRecord) -> int:
        """Score how well a record matches the search. Lower is better."""
        norm_record = self.normalizer.normalize_for_storage(record.name)
        if norm_record.startswith(norm_search):
            return 0
        if norm_search in norm_record:
            return 1
        search_tokens = set(norm_search.split())
        record_tokens = set(norm_record.split())
        overlap = len(search_tokens & record_tokens)
        return len(search_tokens) - overlap
