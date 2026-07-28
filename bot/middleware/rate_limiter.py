"""
Thanaweya Amma Bot — Rate Limiter Middleware
Token-bucket rate limiting per user.
"""

import time
import logging
from collections import defaultdict
from typing import Optional

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update, Message

logger = logging.getLogger(__name__)


class RateLimiter(BaseMiddleware):
    """
    Token-bucket rate limiter per Telegram user.

    Limits:
    - burst: max requests allowed instantly
    - per_minute: sustained rate per minute
    - per_hour: sustained rate per hour
    """

    def __init__(self, burst: int = 5, per_minute: int = 30, per_hour: int = 200):
        super().__init__()
        self.burst = burst
        self.per_minute = per_minute
        self.per_hour = per_hour

        # user_id -> {"tokens": float, "last_refill": float, "minute_count": int, ...}
        self._buckets: dict = defaultdict(self._new_bucket)
        self._lock = __import__("threading").Lock()

    @staticmethod
    def _new_bucket() -> dict:
        now = time.time()
        return {
            "tokens": 5.0,
            "last_refill": now,
            "minute_count": 0,
            "minute_start": now,
            "hour_count": 0,
            "hour_start": now,
        }

    def _check(self, user_id: int) -> bool:
        """Returns True if the request is allowed."""
        now = time.time()
        with self._lock:
            bucket = self._buckets[user_id]

            # Refill tokens
            elapsed = now - bucket["last_refill"]
            bucket["tokens"] = min(
                self.burst, bucket["tokens"] + elapsed * (self.per_minute / 60.0)
            )
            bucket["last_refill"] = now

            # Check minute limit
            if now - bucket["minute_start"] >= 60:
                bucket["minute_count"] = 0
                bucket["minute_start"] = now
            if bucket["minute_count"] >= self.per_minute:
                return False

            # Check hour limit
            if now - bucket["hour_start"] >= 3600:
                bucket["hour_count"] = 0
                bucket["hour_start"] = now
            if bucket["hour_count"] >= self.per_hour:
                return False

            # Consume token
            if bucket["tokens"] >= 1.0:
                bucket["tokens"] -= 1.0
                bucket["minute_count"] += 1
                bucket["hour_count"] += 1
                return True

            return False

    async def __call__(self, handler, event: TelegramObject, data: dict):
        user_id = None
        if isinstance(event, Update) and event.message:
            user_id = event.message.from_user.id

        # Admins bypass rate limiting
        from ..app_state import get_config
        config = get_config()
        if user_id and user_id in config.bot.admin_ids:
            return await handler(event, data)

        if user_id and not self._check(user_id):
            logger.warning(f"Rate limited user {user_id}")
            if isinstance(event, Update) and event.message:
                await event.message.answer(
                    "⏳ أنت ترسل الطلبات بسرعة كبيرة.\n"
                    "يرجى الانتظار قليلاً ثم المحاولة مرة أخرى.",
                )
            return

        return await handler(event, data)