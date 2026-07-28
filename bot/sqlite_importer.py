"""
Thanaweya Amma Bot — SQLite Importer
Loads student records from a SQLite database (converted from .accdb).
"""

import time
import sqlite3
import logging
from pathlib import Path
from typing import List, Optional, Tuple

from .models import StudentRecord, ImportStats
from .search_engine import SearchEngine

logger = logging.getLogger(__name__)


class SQLiteImporter:
    """
    Imports student records from a SQLite database into the SearchEngine.

    The SQLite DB is expected to have:
    - `students` table: seating_no, arabic_name, total_degree, student_case,
                        student_case_desc, c_flage
    - `student_subjects` table: seating_no, arabic_name, s1, s10, s14,
                                student_case, student_case_desc
    """

    def __init__(self, search_engine: SearchEngine, cache_dir: str):
        self.search_engine = search_engine
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._last_import_stats: Optional[ImportStats] = None

    def import_file(
        self, filepath: Path, atomic: bool = True
    ) -> Tuple[Optional[List[StudentRecord]], ImportStats]:
        """
        Import records from a SQLite database file.

        Args:
            filepath: Path to the .db SQLite file
            atomic: If True, only replace data on success

        Returns:
            Tuple of (records, import_stats)
        """
        start_time = time.time()
        stats = ImportStats(file_path=str(filepath))

        try:
            logger.info(f"Opening SQLite database: {filepath}")
            conn = sqlite3.connect(str(filepath))
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            # Get total count
            cur.execute("SELECT COUNT(*) FROM students")
            stats.total_rows = cur.fetchone()[0]
            logger.info(f"Total students: {stats.total_rows:,}")

            # Load subject scores into a lookup dict
            logger.info("Loading subject scores...")
            subject_scores = {}
            try:
                cur.execute("SELECT * FROM student_subjects")
                for row in cur:
                    subject_scores[row["seating_no"]] = {
                        "s1": row["s1"],
                        "s10": row["s10"],
                        "s14": row["s14"],
                    }
                logger.info(f"Loaded {len(subject_scores):,} subject records")
            except sqlite3.OperationalError:
                logger.warning("No student_subjects table found")

            # Load all students
            logger.info("Loading student records...")
            cur.execute("SELECT * FROM students")
            columns = [desc[0] for desc in cur.description]
            stats.columns = columns

            records: List[StudentRecord] = []
            seen_seats = set()

            for row in cur:
                try:
                    seating_no = int(row["seating_no"])
                    arabic_name = str(row["arabic_name"] or "").strip()

                    if not arabic_name or seating_no <= 0:
                        continue

                    total_degree = float(row["total_degree"] or 0)
                    student_case = int(row["student_case"] or 0)
                    student_case_desc = str(
                        row["student_case_desc"] or ""
                    ).strip()
                    c_flage = float(row["c_flage"] or 0)

                    # Build extra fields from subject scores
                    extra = {}
                    if seating_no in subject_scores:
                        scores = subject_scores[seating_no]
                        if scores.get("s1") is not None:
                            extra["المادة 1"] = scores["s1"]
                        if scores.get("s10") is not None:
                            extra["المادة 10"] = scores["s10"]
                        if scores.get("s14") is not None:
                            extra["المادة 14"] = scores["s14"]

                    if seating_no in seen_seats:
                        stats.duplicate_seats += 1
                    seen_seats.add(seating_no)

                    records.append(
                        StudentRecord(
                            seat_number=seating_no,
                            name=arabic_name,
                            grade=total_degree,
                            student_case=student_case,
                            student_case_desc=student_case_desc,
                            c_flag=int(c_flage),
                            extra_fields=extra if extra else {},
                        )
                    )
                except Exception as e:
                    logger.debug(f"Skipping invalid row: {e}")
                    continue

            conn.close()

            stats.valid_rows = len(records)
            logger.info(f"Loaded {stats.valid_rows:,} valid records")

            # Build search indexes
            logger.info("Building search indexes...")
            self.search_engine.load_records(records)
            logger.info(
                f"Indexes built: {self.search_engine.total_records:,} records"
            )

            stats.import_time_seconds = time.time() - start_time
            self._last_import_stats = stats

            logger.info(
                f"SQLite import completed in {stats.import_time_seconds:.2f}s — "
                f"{stats.valid_rows:,} records, "
                f"{stats.duplicate_seats:,} duplicates"
            )

            return records, stats

        except Exception as e:
            stats.error = str(e)
            stats.import_time_seconds = time.time() - start_time
            logger.error(f"SQLite import failed: {e}", exc_info=True)
            raise

    def try_load_cache(self, source_file: Path) -> bool:
        """SQLite doesn't need caching — it's already fast enough."""
        return False

    @property
    def last_import_stats(self) -> Optional[ImportStats]:
        return self._last_import_stats
