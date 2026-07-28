"""
Thanaweya Amma Bot — Excel Importer
Validates, imports, and indexes Excel files with caching support.
"""

import time
import pickle
import hashlib
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import polars as pl

from .models import StudentRecord, ImportStats
from .search_engine import SearchEngine
from .arabic_normalizer import ArabicNormalizer

logger = logging.getLogger(__name__)


class ExcelImporter:
    """
    Handles Excel file validation, import, and index building.

    Features:
    - Fast import using Polars (lazy loading)
    - Column auto-detection by header names
    - Duplicate detection
    - Atomic data replacement with rollback
    - Pickle-based cache for fast restart
    """

    REQUIRED_COLUMNS = {"رقم الجلوس", "الاسم"}
    ALTERNATIVE_SEAT_NAMES = {"seat_number", "Seat Number", "جلوس"}
    ALTERNATIVE_NAME_NAMES = {"name", "Name", "الاسم بالكامل"}

    def __init__(self, search_engine: SearchEngine, cache_dir: str):
        self.search_engine = search_engine
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._import_lock = __import__("threading").Lock()
        self._last_import_stats: Optional[ImportStats] = None

    def _file_hash(self, filepath) -> str:
        """Compute a fast hash of the file for cache invalidation.
        Uses filename + size only (not mtime) so cache survives file copies/touches.
        """
        p = Path(filepath)
        h = hashlib.md5()
        h.update(p.name.encode("utf-8"))
        h.update(str(p.stat().st_size).encode("utf-8"))
        return h.hexdigest()

    def _cache_path(self, file_hash: str) -> Path:
        return self.cache_dir / f"index_{file_hash}.pkl"

    def try_load_cache(self, source_file: Path) -> bool:
        """Try to load from cache. Returns True if cache was loaded."""
        if not source_file.exists():
            return False

        try:
            file_hash = self._file_hash(source_file)
            cache_file = self._cache_path(file_hash)

            if not cache_file.exists():
                return False

            logger.info(f"Loading cached index from {cache_file}")
            start = time.time()

            with open(cache_file, "rb") as f:
                cached = pickle.load(f)

            stats = cached["stats"]

            # Fast path: pre-built indexes available (v2 cache)
            if "indexes" in cached:
                idx = cached["indexes"]
                self.search_engine.load_indexes_direct(
                    seat_index=idx["seat_index"],
                    name_index=idx["name_index"],
                    name_tokens_index=idx["name_tokens_index"],
                    total=idx["total_records"],
                )
            else:
                # Slow path: rebuild indexes from records (v1 cache)
                records = cached["records"]
                self.search_engine.load_records(records)

            elapsed = time.time() - start
            logger.info(
                f"Cache loaded in {elapsed:.2f}s — "
                f"{self.search_engine.total_records:,} records"
            )
            self._last_import_stats = stats
            return True

        except Exception as e:
            logger.warning(f"Cache load failed: {e}, will do full import")
            return False

    def import_file(
        self, filepath: Path, atomic: bool = True
    ) -> Tuple[Optional[List[StudentRecord]], ImportStats]:
        """
        Import an Excel file, validate it, and build search indexes.

        Args:
            filepath: Path to the .xlsx file
            atomic: If True, only replace data on success

        Returns:
            Tuple of (records, import_stats)
        """
        start_time = time.time()
        stats = ImportStats(file_path=str(filepath))

        with self._import_lock:
            try:
                # Step 1: Read Excel with Polars (very fast)
                logger.info(f"Reading Excel file: {filepath}")
                df = pl.read_excel(filepath)
                stats.columns = df.columns

                # Convert to dict of lists for processing
                total_rows = len(df)
                stats.total_rows = total_rows
                logger.info(f"Read {total_rows:,} rows with columns: {stats.columns}")

                # Step 2: Detect and map columns
                column_map = self._detect_columns(df.columns)
                logger.info(f"Column mapping: {column_map}")

                # Step 3: Validate required columns
                if not self._validate_columns(column_map):
                    raise ValueError(
                        f"Missing required columns. Need seat number and name. "
                        f"Found columns: {list(df.columns)}"
                    )

                # Step 4: Convert to records
                records = self._df_to_records(df, column_map)
                del df  # Free DataFrame memory immediately
                stats.valid_rows = len(records)

                # Step 5: Detect duplicates
                seen_seats = set()
                for r in records:
                    if r.seat_number in seen_seats:
                        stats.duplicate_seats += 1
                    seen_seats.add(r.seat_number)

                if stats.duplicate_seats > 0:
                    logger.warning(f"Found {stats.duplicate_seats:,} duplicate seat numbers")

                # Step 6: Build search indexes
                logger.info("Building search indexes...")
                dup_count = self.search_engine.load_records(records)
                logger.info(
                    f"Indexes built: {self.search_engine.total_records:,} records indexed"
                )

                # Step 7: Save cache
                self._save_cache(filepath, records, stats)

                stats.import_time_seconds = time.time() - start_time
                self._last_import_stats = stats

                logger.info(
                    f"Import completed in {stats.import_time_seconds:.2f}s — "
                    f"{stats.valid_rows:,} records, "
                    f"{stats.duplicate_seats:,} duplicates"
                )

                return records, stats

            except Exception as e:
                stats.error = str(e)
                stats.import_time_seconds = time.time() - start_time
                logger.error(f"Import failed: {e}", exc_info=True)
                raise

    def _detect_columns(self, columns: List[str]) -> Dict[str, str]:
        """
        Auto-detect column mapping based on header names.
        Returns a mapping from standard keys to actual column names.
        """
        col_lower = {c.lower().strip(): c for c in columns}
        mapping = {}

        # Seat number
        for name in ["رقم الجلوس", "seat_number", "seat number", "جلوس"]:
            if name in col_lower:
                mapping["seat"] = col_lower[name]
                break
            if name in columns:
                mapping["seat"] = name
                break
        if "seat" not in mapping:
            # Fuzzy: find column containing "جلوس" or "seat"
            for c in columns:
                if "جلوس" in c or "seat" in c.lower():
                    mapping["seat"] = c
                    break

        # Name
        for name in ["الاسم", "name", "الاسم بالكامل"]:
            if name in col_lower:
                mapping["name"] = col_lower[name]
                break
            if name in columns:
                mapping["name"] = name
                break
        if "name" not in mapping:
            for c in columns:
                if "اسم" in c or "name" in c.lower():
                    mapping["name"] = c
                    break

        # Grade
        for name in ["الدرجة", "grade", "المجموع", "الدرجة الكلية"]:
            if name in col_lower:
                mapping["grade"] = col_lower[name]
                break
            if name in columns:
                mapping["grade"] = name
                break

        # Student case
        for name in ["student_case", "حالة الطالب"]:
            if name in col_lower:
                mapping["student_case"] = col_lower[name]
                break
            if name in columns:
                mapping["student_case"] = name
                break

        # Student case description
        for name in ["student_case_desc", "وصف الحالة"]:
            if name in col_lower:
                mapping["student_case_desc"] = col_lower[name]
                break
            if name in columns:
                mapping["student_case_desc"] = name
                break

        # C flag
        for name in ["c_flage", "c_flag", "العلامة"]:
            if name in col_lower:
                mapping["c_flag"] = col_lower[name]
                break
            if name in columns:
                mapping["c_flag"] = name
                break

        return mapping

    def _validate_columns(self, column_map: Dict[str, str]) -> bool:
        """Check that required columns are mapped."""
        return "seat" in column_map and "name" in column_map

    def _df_to_records(
        self, df: pl.DataFrame, column_map: Dict[str, str]
    ) -> List[StudentRecord]:
        """Convert Polars DataFrame to list of StudentRecord.
        Uses column-wise access (no to_dicts) to save memory on large datasets.
        """
        records = []

        # Get actual column names
        seat_col = column_map.get("seat")
        name_col = column_map.get("name")
        grade_col = column_map.get("grade")
        case_col = column_map.get("student_case")
        case_desc_col = column_map.get("student_case_desc")
        flag_col = column_map.get("c_flag")

        # Extract columns as Python lists (avoids to_dicts overhead)
        n = len(df)
        seats = df[seat_col].to_list()
        names = df[name_col].to_list()
        grades = df[grade_col].to_list() if grade_col else [None] * n
        cases = df[case_col].to_list() if case_col else [None] * n
        case_descs = df[case_desc_col].to_list() if case_desc_col else [None] * n
        flags = df[flag_col].to_list() if flag_col else [None] * n

        mapped_cols = {seat_col, name_col, grade_col, case_col, case_desc_col, flag_col}
        extra_cols = [c for c in df.columns if c not in mapped_cols]
        extra_data = {c: df[c].to_list() for c in extra_cols}

        for i in range(n):
            try:
                seat = int(float(seats[i] or 0))
                name = str(names[i] or "").strip()
                if not name or seat <= 0:
                    continue

                grade = 0.0
                if grades[i] is not None:
                    try:
                        grade = float(grades[i])
                    except (ValueError, TypeError):
                        pass

                student_case = 0
                if cases[i] is not None:
                    try:
                        student_case = int(cases[i])
                    except (ValueError, TypeError):
                        pass

                case_desc = str(case_descs[i] or "").strip() if case_descs[i] is not None else ""

                c_flag = 0
                if flags[i] is not None:
                    try:
                        c_flag = int(flags[i])
                    except (ValueError, TypeError):
                        pass

                extra = {}
                for c in extra_cols:
                    v = extra_data[c][i]
                    if v is not None:
                        extra[c] = v

                records.append(
                    StudentRecord(
                        seat_number=seat,
                        name=name,
                        grade=grade,
                        student_case=student_case,
                        student_case_desc=case_desc,
                        c_flag=c_flag,
                        extra_fields=extra if extra else {},
                    )
                )
            except Exception as e:
                logger.debug(f"Skipping invalid row {i}: {e}")
                continue

        return records

    def _save_cache(
        self, source_file: Path, records: List[StudentRecord], stats: ImportStats
    ) -> None:
        """Save processed data to cache for fast restart."""
        try:
            file_hash = self._file_hash(source_file)
            cache_file = self._cache_path(file_hash)

            # Write to temp file first, then rename (atomic on POSIX)
            tmp_file = cache_file.with_suffix(".tmp")
            # Save with pre-built indexes for instant startup
            indexes = self.search_engine.dump_indexes()
            with open(tmp_file, "wb") as f:
                pickle.dump(
                    {"indexes": indexes, "stats": stats},
                    f, protocol=pickle.HIGHEST_PROTOCOL,
                )
            tmp_file.rename(cache_file)

            # Clean old cache files
            for old_cache in self.cache_dir.glob("index_*.pkl"):
                if old_cache != cache_file:
                    old_cache.unlink(missing_ok=True)
                    logger.info(f"Cleaned old cache: {old_cache}")

            logger.info(f"Cache saved to {cache_file}")
        except Exception as e:
            logger.warning(f"Cache save failed: {e}")

    @property
    def last_import_stats(self) -> Optional[ImportStats]:
        return self._last_import_stats