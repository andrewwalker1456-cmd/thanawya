"""
Thanaweya Amma Bot — Statistics Service
Tracks runtime metrics for admin dashboard.
"""

import time
import threading
from collections import defaultdict, deque
from datetime import datetime, date
from typing import Dict, List, Tuple, Optional

import psutil


class StatsService:
    """Thread-safe statistics tracking service."""

    def __init__(self):
        self._lock = threading.Lock()
        self._total_searches = 0
        self._seat_searches = 0
        self._name_searches = 0
        self._successful_searches = 0
        self._failed_searches = 0
        self._search_times: deque = deque(maxlen=1000)
        self._most_searched_seats: Dict[int, int] = defaultdict(int)
        self._most_searched_names: Dict[str, int] = defaultdict(int)
        self._today_searches = 0
        self._today_date: date = date.today()
        self._import_history: List[dict] = []
        self._errors: deque = deque(maxlen=200)
        self._start_time = time.time()

    def record_search(
        self,
        search_type: str,
        query: str,
        found: bool,
        duration_ms: float,
    ) -> None:
        """Record a search event."""
        with self._lock:
            self._total_searches += 1
            self._today_searches += 1

            # Reset daily counter
            today = date.today()
            if today != self._today_date:
                self._today_date = today
                self._today_searches = 1

            if search_type == "seat":
                self._seat_searches += 1
                try:
                    self._most_searched_seats[int(query)] += 1
                except (ValueError, TypeError):
                    pass
            elif search_type == "name":
                self._name_searches += 1
                self._most_searched_names[query] += 1

            if found:
                self._successful_searches += 1
            else:
                self._failed_searches += 1

            self._search_times.append(duration_ms)

    def record_import(self, stats: dict) -> None:
        """Record an import event."""
        with self._lock:
            self._import_history.append({
                "time": datetime.now().isoformat(),
                "file": stats.get("file_path", ""),
                "rows": stats.get("valid_rows", 0),
                "duplicates": stats.get("duplicate_seats", 0),
                "duration": stats.get("import_time_seconds", 0),
                "error": stats.get("error"),
            })

    def record_error(self, error: str) -> None:
        """Record an error event."""
        with self._lock:
            self._errors.append({
                "time": datetime.now().isoformat(),
                "error": error,
            })

    def get_stats(self) -> dict:
        """Get all statistics for the admin dashboard."""
        with self._lock:
            avg_time = (
                sum(self._search_times) / len(self._search_times)
                if self._search_times
                else 0
            )

            # Get top searched
            top_seats = sorted(
                self._most_searched_seats.items(), key=lambda x: -x[1]
            )[:10]
            top_names = sorted(
                self._most_searched_names.items(), key=lambda x: -x[1]
            )[:10]

            # System health
            process = psutil.Process()
            memory_mb = process.memory_info().rss / (1024 * 1024)
            uptime_seconds = time.time() - self._start_time

            return {
                "total_searches": self._total_searches,
                "seat_searches": self._seat_searches,
                "name_searches": self._name_searches,
                "successful_searches": self._successful_searches,
                "failed_searches": self._failed_searches,
                "today_searches": self._today_searches,
                "avg_search_time_ms": round(avg_time, 2),
                "top_searched_seats": top_seats,
                "top_searched_names": top_names,
                "import_history": list(self._import_history)[-10:],
                "recent_errors": list(self._errors)[-20:],
                "system": {
                    "memory_mb": round(memory_mb, 1),
                    "uptime_seconds": round(uptime_seconds),
                    "process_id": process.pid,
                },
            }