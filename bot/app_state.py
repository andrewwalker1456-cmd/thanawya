"""
Thanaweya Amma Bot — Application State
Centralizes all singleton instances to avoid circular imports.
"""

import logging
from typing import Optional

from .config import load_config, AppConfig

logger = logging.getLogger(__name__)

# ── Global singletons (lazy-initialized) ────────────────────────

_config: Optional[AppConfig] = None
_search_engine = None
_pdf_generator = None
_importer = None
_stats_service = None


def get_config() -> AppConfig:
    """Get or create the global config singleton."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def get_search_engine():
    """Get the global search engine instance."""
    global _search_engine
    if _search_engine is None:
        from .search_engine import SearchEngine
        from pathlib import Path
        cfg = get_config()
        db_path = Path(cfg.base_dir).parent / cfg.data.source_file
        _search_engine = SearchEngine(
            db_path=str(db_path),
            normalize_teh=cfg.search.normalize_teh
        )
    return _search_engine


def get_pdf_generator():
    """Get the global PDF generator instance."""
    global _pdf_generator
    if _pdf_generator is None:
        from .pdf_generator import PDFGenerator
        cfg = get_config()
        _pdf_generator = PDFGenerator(
            font_path=cfg.pdf.font_path,
            fallback_font_path=cfg.pdf.fallback_font_path,
        )
    return _pdf_generator


def get_importer():
    """Get the global importer instance (SQLite or Excel based on source file)."""
    global _importer
    if _importer is None:
        cfg = get_config()
        source = cfg.data.source_file
        if source and source.endswith(".db"):
            from .sqlite_importer import SQLiteImporter
            _importer = SQLiteImporter(
                search_engine=get_search_engine(),
                cache_dir=cfg.data.cache_dir,
            )
        else:
            from .excel_importer import ExcelImporter
            _importer = ExcelImporter(
                search_engine=get_search_engine(),
                cache_dir=cfg.data.cache_dir,
            )
    return _importer


def get_stats_service():
    """Get the global stats service instance."""
    global _stats_service
    if _stats_service is None:
        from .services.stats_service import StatsService
        _stats_service = StatsService()
    return _stats_service


