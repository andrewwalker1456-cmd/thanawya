"""
Thanaweya Amma Bot — Search Engine
High-performance in-memory search with optimized indexes.
"""

import threading
from collections import defaultdict
from typing import Dict, List, Optional

from .arabic_normalizer import ArabicNormalizer
from .models import StudentRecord


class SearchEngine:
    """
    Thread-safe, in-memory search engine with pre-built indexes.

    Indexes:
    - seat_index: dict[int, StudentRecord] — O(1) lookup by seat number
    - name_index: dict[str, list[StudentRecord]] — O(1) exact normalized name lookup
    - name_tokens_index: dict[str, list[StudentRecord]] — token-based name search
      Uses enhanced tokenization that handles:
      - Fused compounds: عبدالرحمن produces tokens [عبدالرحمن, عبد, الرحمن, رحمن]
      - ال prefix stripping: الرحمن also indexes under رحمن
      - ة/ه equivalence at end of words
    """

    def __init__(self, normalize_teh: bool = False):
        self.normalizer = ArabicNormalizer(normalize_teh=normalize_teh)
        self._seat_index: Dict[int, StudentRecord] = {}
        self._name_index: Dict[str, List[StudentRecord]] = defaultdict(list)
        self._name_tokens_index: Dict[str, List[StudentRecord]] = defaultdict(list)
        self._lock = threading.RLock()
        self._total_records = 0

    @property
    def total_records(self) -> int:
        return self._total_records

    def load_records(self, records: List[StudentRecord]) -> None:
        """
        Build all search indexes from a list of records.
        Uses enhanced tokenization for Arabic name matching.
        """
        seat_index: Dict[int, StudentRecord] = {}
        name_index: Dict[str, List[StudentRecord]] = defaultdict(list)
        name_tokens_index: Dict[str, List[StudentRecord]] = defaultdict(list)

        duplicate_count = 0

        for record in records:
            # Seat number index
            if record.seat_number in seat_index:
                duplicate_count += 1
            seat_index[record.seat_number] = record

            # Normalized name index (exact match)
            norm_name = self.normalizer.normalize_for_storage(record.name)
            name_index[norm_name].append(record)

            # Enhanced token-based index
            tokens = self.normalizer.get_search_tokens(record.name)
            for token in tokens:
                name_tokens_index[token].append(record)

        with self._lock:
            self._seat_index = seat_index
            self._name_index = dict(name_index)
            self._name_tokens_index = dict(name_tokens_index)
            self._total_records = len(seat_index)

        return duplicate_count

    def search_by_seat(self, seat_number: int) -> Optional[StudentRecord]:
        """O(1) lookup by seat number."""
        with self._lock:
            return self._seat_index.get(seat_number)

    def search_by_name(self, name: str) -> List[StudentRecord]:
        """
        Search by full Arabic name.

        Strategy:
        1. Try exact normalized name match first
        2. Fall back to intersection of enhanced token matches
           (handles عبدالرحمن vs عبد الرحمن, ة/ه, etc.)
        3. If strict intersection yields nothing, relax to best-effort (any 2+ tokens)
        """
        norm_name = self.normalizer.normalize_for_search(name)

        with self._lock:
            # Strategy 1: Exact match
            if norm_name in self._name_index:
                return list(self._name_index[norm_name])

            # Strategy 2: Enhanced token intersection
            tokens = self.normalizer.get_search_tokens(name)
            if not tokens:
                return []

            # Find candidates for each token
            token_results = []
            for token in tokens:
                candidates = self._name_tokens_index.get(token, [])
                if candidates:
                    token_results.append(set(id(r) for r in candidates))

            if not token_results:
                return []

            # Intersect all token result sets
            common_ids = token_results[0]
            for tr in token_results[1:]:
                common_ids = common_ids & tr

            results = []
            if common_ids:
                # Build lookup from id to record
                id_to_record = {}
                for token in tokens:
                    for r in self._name_tokens_index.get(token, []):
                        if id(r) in common_ids:
                            id_to_record[id(r)] = r
                results = list(id_to_record.values())
            else:
                # Strategy 3: Relax — union of all candidates, score by overlap
                all_ids = set()
                id_to_record = {}
                for token in tokens:
                    for r in self._name_tokens_index.get(token, []):
                        rid = id(r)
                        all_ids.add(rid)
                        id_to_record[rid] = r
                results = list(id_to_record.values())

            # Score and sort results
            results.sort(key=lambda r: self._name_similarity_score(norm_name, r))
            return results

    def _name_similarity_score(self, norm_search: str, record: StudentRecord) -> int:
        """Score how well a record matches the search. Lower is better."""
        norm_record = self.normalizer.normalize_for_storage(record.name)
        # Exact prefix match is best
        if norm_record.startswith(norm_search):
            return 0
        # Contains match
        if norm_search in norm_record:
            return 1
        # Token overlap count (lower is better)
        search_tokens = set(norm_search.split())
        record_tokens = set(norm_record.split())
        overlap = len(search_tokens & record_tokens)
        return len(search_tokens) - overlap

    def load_indexes_direct(self, seat_index: dict, name_index: dict,
                                  name_tokens_index: dict, total: int) -> None:
        """Restore indexes from pre-built cache (skips tokenization).
        Much faster than load_records for startup.
        """
        with self._lock:
            self._seat_index = seat_index
            self._name_index = name_index
            self._name_tokens_index = name_tokens_index
            self._total_records = total

    def dump_indexes(self) -> dict:
        """Export current indexes for caching."""
        with self._lock:
            return {
                "seat_index": self._seat_index,
                "name_index": self._name_index,
                "name_tokens_index": self._name_tokens_index,
                "total_records": self._total_records,
            }

    def get_stats(self) -> dict:
        """Return search engine statistics."""
        with self._lock:
            return {
                "total_records": self._total_records,
                "unique_names": len(self._name_index),
                "unique_tokens": len(self._name_tokens_index),
            }

    def is_loaded(self) -> bool:
        """Check if data is loaded."""
        with self._lock:
            return self._total_records > 0
