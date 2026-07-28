"""
Thanaweya Amma Bot — Configuration Manager
Loads config from YAML file with environment variable overrides.
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List
import yaml


@dataclass
class BotConfig:
    token: str = ""
    admin_ids: List[int] = field(default_factory=list)


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8080


@dataclass
class DataConfig:
    upload_dir: str = "data/uploads"
    cache_dir: str = "data/cache"
    source_file: str = ""


@dataclass
class SearchConfig:
    normalize_teh: bool = False
    max_name_results: int = 10


@dataclass
class RateLimitConfig:
    max_requests_per_minute: int = 30
    max_requests_per_hour: int = 200
    burst: int = 5


@dataclass
class PdfConfig:
    font_path: str = "fonts/NotoNaskhArabic.ttf"
    fallback_font_path: str = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    paper_size: str = "A4"


@dataclass
class LoggingConfig:
    level: str = "INFO"
    file: str = "logs/bot.log"
    max_size_mb: int = 50
    backup_count: int = 5


@dataclass
class AdminConfig:
    max_upload_size_mb: int = 100


@dataclass
class PaymentConfig:
    enabled: bool = False
    price_egp: float = 20.0
    provider: str = "ammerpay"
    ammerpay_test_key: str = ""
    ammerpay_live_key: str = ""
    ammerpay_use_test: bool = True
    free_searches_per_user: int = 0
    admin_free: bool = True


@dataclass
class AppConfig:
    bot: BotConfig = field(default_factory=BotConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    data: DataConfig = field(default_factory=DataConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    pdf: PdfConfig = field(default_factory=PdfConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    admin: AdminConfig = field(default_factory=AdminConfig)
    payment: PaymentConfig = field(default_factory=PaymentConfig)
    base_dir: Path = field(default_factory=lambda: Path(__file__).parent)


def load_config(config_path = None) -> AppConfig:
    """Load configuration from YAML file with environment variable overrides."""
    if config_path is None:
        config_path = Path(__file__).parent / "config.yaml"

    config_path = Path(config_path)
    raw = {}

    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

    # Load .env file manually if it exists (for local running)
    env_path = config_path.parent.parent / ".env"
    if env_path.exists():
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        if k not in os.environ:
                            os.environ[k] = v.strip()
        except Exception:
            pass

    def get(d: dict, key: str, default=None):
        return d.get(key, default) if d else default

    # Bot config
    bot_token = os.environ.get("BOT_TOKEN", get(raw, "bot", {}).get("token", ""))
    admin_ids_str = os.environ.get("ADMIN_IDS", "")
    admin_ids = (
        [int(x.strip()) for x in admin_ids_str.split(",") if x.strip()]
        if admin_ids_str
        else get(raw, "bot", {}).get("admin_ids", [])
    )

    # Data source file from env
    source_file = os.environ.get("SOURCE_FILE", get(raw, "data", {}).get("source_file", ""))

    cfg = AppConfig(
        bot=BotConfig(token=bot_token, admin_ids=admin_ids),
        server=ServerConfig(
            host=get(raw, "server", {}).get("host", "0.0.0.0"),
            port=get(raw, "server", {}).get("port", 8080),
        ),
        data=DataConfig(
            upload_dir=get(raw, "data", {}).get("upload_dir", "data/uploads"),
            cache_dir=get(raw, "data", {}).get("cache_dir", "data/cache"),
            source_file=source_file,
        ),
        search=SearchConfig(
            normalize_teh=get(raw, "search", {}).get("normalize_teh", False),
            max_name_results=get(raw, "search", {}).get("max_name_results", 10),
        ),
        rate_limit=RateLimitConfig(
            max_requests_per_minute=get(raw, "rate_limit", {}).get("max_requests_per_minute", 30),
            max_requests_per_hour=get(raw, "rate_limit", {}).get("max_requests_per_hour", 200),
            burst=get(raw, "rate_limit", {}).get("burst", 5),
        ),
        pdf=PdfConfig(
            font_path=get(raw, "pdf", {}).get("font_path", "fonts/NotoNaskhArabic.ttf"),
            fallback_font_path=get(raw, "pdf", {}).get(
                "fallback_font_path",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            ),
            paper_size=get(raw, "pdf", {}).get("paper_size", "A4"),
        ),
        logging=LoggingConfig(
            level=os.environ.get("LOG_LEVEL", get(raw, "logging", {}).get("level", "INFO")),
            file=get(raw, "logging", {}).get("file", "logs/bot.log"),
            max_size_mb=get(raw, "logging", {}).get("max_size_mb", 50),
            backup_count=get(raw, "logging", {}).get("backup_count", 5),
        ),
        admin=AdminConfig(
            max_upload_size_mb=get(raw, "admin", {}).get("max_upload_size_mb", 100),
        ),
        payment=PaymentConfig(
            enabled=False,  # Payment disabled
        ),
        base_dir=Path(__file__).parent,
    )

    # Resolve paths relative to base_dir
    cfg.data.upload_dir = str(cfg.base_dir / cfg.data.upload_dir)
    cfg.data.cache_dir = str(cfg.base_dir / cfg.data.cache_dir)
    cfg.pdf.font_path = str(cfg.base_dir / cfg.pdf.font_path)

    return cfg