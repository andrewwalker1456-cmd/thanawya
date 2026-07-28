"""
Thanaweya Amma Bot — Main Entry Point
Initializes all components and starts the Telegram bot.
"""

import asyncio
import logging
import os
import sys
import signal
from pathlib import Path
from logging.handlers import RotatingFileHandler

from aiohttp import web

from aiogram.fsm.context import FSMContext
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from .app_state import get_config, get_search_engine, get_importer, get_stats_service
from .config import AppConfig


def setup_logging(config: AppConfig) -> None:
    """Configure logging with rotation."""
    log_path = Path(config.base_dir) / config.logging.file
    log_path.parent.mkdir(parents=True, exist_ok=True)

    fmt = "%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s"
    date_fmt = "%Y-%m-%d %H:%M:%S"

    # Root logger
    root = logging.getLogger()
    root.setLevel(getattr(logging, config.logging.level, logging.INFO))

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter(fmt, datefmt=date_fmt))
    root.addHandler(console)

    # File handler with rotation
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=config.logging.max_size_mb * 1024 * 1024,
        backupCount=config.logging.backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(fmt, datefmt=date_fmt))
    root.addHandler(file_handler)

    # Suppress noisy loggers
    logging.getLogger("aiogram").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("polars").setLevel(logging.WARNING)


async def initial_import(config: AppConfig) -> None:
    """Perform initial data import from configured source."""
    importer = get_importer()
    stats_service = get_stats_service()
    logger = logging.getLogger(__name__)

    # Try source file first (env var or config)
    source = config.data.source_file
    if source:
        source_path = Path(source)
        # Also try relative to base_dir
        if not source_path.exists():
            source_path = Path(config.base_dir).parent / source
        if source_path.exists():
            logger.info(f"Importing from source file: {source_path}")
            try:
                _, stats = importer.import_file(source_path)
                stats_service.record_import({
                    "file_path": str(source_path),
                    "valid_rows": stats.valid_rows,
                    "duplicate_seats": stats.duplicate_seats,
                    "import_time_seconds": stats.import_time_seconds,
                })
                return
            except Exception as e:
                logger.error(f"Source file import failed: {e}", exc_info=True)

    # Try upload directory
    upload_dir = Path(config.data.upload_dir)
    if upload_dir.exists():
        xlsx_files = sorted(
            upload_dir.glob("*.xlsx"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if xlsx_files:
            latest = xlsx_files[0]
            logger.info(f"Importing from upload: {latest}")

            # Try cache first
            if importer.try_load_cache(latest):
                logger.info("Loaded from cache successfully")
                return

            try:
                _, stats = importer.import_file(latest)
                stats_service.record_import({
                    "file_path": str(latest),
                    "valid_rows": stats.valid_rows,
                    "duplicate_seats": stats.duplicate_seats,
                    "import_time_seconds": stats.import_time_seconds,
                })
            except Exception as e:
                logger.error(f"Upload import failed: {e}", exc_info=True)
        else:
            logger.warning("No .xlsx files found in upload directory")
    else:
        logger.warning("Upload directory does not exist")

    # Final check
    engine = get_search_engine()
    if not engine.is_loaded():
        logger.warning(
            "No data loaded! Admin must upload an Excel file via /admin."
        )


async def main() -> None:
    """Main entry point — loads config, imports data, starts bot."""
    config = get_config()
    setup_logging(config)
    logger = logging.getLogger(__name__)

    if not config.bot.token:
        logger.error(
            "No BOT_TOKEN set. Set it via BOT_TOKEN environment variable "
            "or in config.yaml"
        )
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("  Thanaweya Amma Bot — Starting")
    logger.info("=" * 60)

    # Import data
    logger.info("Loading data...")
    await initial_import(config)

    engine = get_search_engine()
    logger.info(f"Search engine ready: {engine.total_records:,} records")

    # Create bot
    bot = Bot(
        token=config.bot.token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # Create dispatcher
    dp = Dispatcher()

    # Register middleware
    from .middleware.rate_limiter import RateLimiter
    from .middleware.force_sub import ForceSubMiddleware
    
    dp.message.middleware(RateLimiter(
        burst=config.rate_limit.burst,
        per_minute=config.rate_limit.max_requests_per_minute,
        per_hour=config.rate_limit.max_requests_per_hour,
    ))
    
    force_sub = ForceSubMiddleware(
        channel_username="@Thanaweya_Amma_Results",
        channel_url="https://t.me/Thanaweya_Amma_Results"
    )
    dp.message.middleware(force_sub)
    dp.callback_query.middleware(force_sub)

    # Register handlers
    from .handlers import get_routers
    for r in get_routers():
        dp.include_router(r)

    # Handle /start
    from aiogram.filters import CommandStart
    from .handlers.dashboard import get_main_keyboard

    @dp.message(CommandStart())
    async def on_start(message, state: FSMContext):
        await state.clear()
        await message.answer(
            "🎓 <b>نتيجة الثانوية العامة 2026</b>\n\n"
            "اختر من القائمة أدناه للبحث عن النتيجة:",
            reply_markup=get_main_keyboard(),
        )

    # Graceful shutdown
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start health check web server for Render
    port = int(os.environ.get("PORT", config.server.port))

    async def health_handler(request):
        engine = get_search_engine()
        return web.json_response({
            "status": "ok",
            "records": engine.total_records if engine else 0,
        })

    app = web.Application()
    app.router.add_get("/", health_handler)
    app.router.add_get("/health", health_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Health check server running on port {port}")

    # Start polling
    logger.info("Bot is running. Press Ctrl+C to stop.")
    try:
        await dp.start_polling(bot)
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception as e:
        logger.critical(f"Polling crashed: {e}", exc_info=True)
    finally:
        try:
            await runner.cleanup()
        except Exception:
            pass
        try:
            await bot.session.close()
        except Exception:
            pass
        logger.info("Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())