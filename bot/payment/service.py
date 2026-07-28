"""
Payment Service — Manages payment state and integrates with AmmerPay.

Flow:
1. User clicks search → payment required
2. Bot creates AmmerPay order → sends payment link
3. User pays → callback marks order as paid
4. User clicks "confirm payment" → bot checks status → shows result

Admins bypass payment.
"""

import time
import logging
import asyncio
from typing import Dict, List, Optional
from dataclasses import dataclass, field

from .ammerpay_client import AmmerPayClient, PaymentOrder

logger = logging.getLogger(__name__)


@dataclass
class UserPayment:
    """Tracks a user's payment for a search."""
    user_id: int
    order: PaymentOrder
    search_type: str = "seat"  # "seat" or "name"
    search_query: str = ""
    verified: bool = False


class PaymentService:
    """Manages payments for search access."""

    def __init__(self, ammerpay_client: AmmerPayClient, price: float = 20.0,
                 admin_free: bool = True, enabled: bool = True):
        self.client = ammerpay_client
        self.price = price
        self.admin_free = admin_free
        self.enabled = enabled

        # In-memory pending payments: order_id -> UserPayment
        self._pending: Dict[str, UserPayment] = {}
        # Paid sessions: user_id -> expiry timestamp
        self._paid_sessions: Dict[int, float] = {}
        # Revenue tracking
        self._total_revenue: float = 0.0
        self._total_payments: int = 0

        # Background cleaner task
        self._clean_task: Optional[asyncio.Task] = None

    def start_background_tasks(self):
        """Start background cleanup task."""
        self._clean_task = asyncio.create_task(self._cleanup_loop())

    async def _cleanup_loop(self):
        """Periodically clean expired pending orders."""
        while True:
            await asyncio.sleep(300)  # every 5 min
            now = time.time()
            expired = [
                oid for oid, up in self._pending.items()
                if now - up.order.created_at > 1800  # 30 min expiry
            ]
            for oid in expired:
                del self._pending[oid]
            # Also clean expired paid sessions (1 hour)
            expired_sessions = [
                uid for uid, exp in self._paid_sessions.items()
                if now > exp
            ]
            for uid in expired_sessions:
                del self._paid_sessions[uid]

    def is_admin_bypass(self, user_id: int, admin_ids: List[int]) -> bool:
        """Check if user is admin and admin bypass is enabled."""
        return self.admin_free and user_id in admin_ids

    def has_paid_session(self, user_id: int) -> bool:
        """Check if user has an active paid session."""
        expiry = self._paid_sessions.get(user_id)
        if expiry and time.time() < expiry:
            return True
        return False

    def mark_paid_session(self, user_id: int, duration_seconds: int = 3600):
        """Grant user a paid session for N seconds (default 1 hour)."""
        self._paid_sessions[user_id] = time.time() + duration_seconds

    async def create_payment(
        self, user_id: int, search_type: str, search_query: str
    ) -> UserPayment:
        """Create a payment for a search request."""
        order_id = f"{int(time.time())}_{user_id}"

        order = await self.client.create_order(
            amount=self.price,
            currency="EGP",
            order_id=order_id,
            description=f"نتيجة الثانوية - {search_type}",
            user_id=user_id,
        )

        user_payment = UserPayment(
            user_id=user_id,
            order=order,
            search_type=search_type,
            search_query=search_query,
        )

        self._pending[order_id] = user_payment
        return user_payment

    def get_pending(self, order_id: str) -> Optional[UserPayment]:
        return self._pending.get(order_id)

    def get_pending_by_user(self, user_id: int) -> Optional[UserPayment]:
        """Get the most recent pending payment for a user."""
        for up in reversed(list(self._pending.values())):
            if up.user_id == user_id and up.order.status == "pending":
                return up
        return None

    async def confirm_payment(self, order_id: str) -> bool:
        """Check payment status and mark as paid if confirmed."""
        up = self._pending.get(order_id)
        if not up:
            return False

        # Check with AmmerPay
        status = await self.client.check_status(order_id)

        if status in ("paid", "completed", "success"):
            up.verified = True
            up.order.status = "paid"
            up.order.paid_at = time.time()

            # Grant paid session
            self.mark_paid_session(up.user_id)

            # Track revenue
            self._total_revenue += up.order.amount
            self._total_payments += 1

            logger.info(
                f"Payment confirmed: order={order_id} "
                f"user={up.user_id} amount={up.order.amount}"
            )
            return True

        return False

    def manual_confirm(self, order_id: str) -> bool:
        """Admin: manually confirm a payment."""
        up = self._pending.get(order_id)
        if not up:
            return False
        up.verified = True
        up.order.status = "paid"
        up.order.paid_at = time.time()
        self.mark_paid_session(up.user_id)
        self._total_revenue += up.order.amount
        self._total_payments += 1
        return True

    def get_stats(self) -> dict:
        return {
            "total_revenue": self._total_revenue,
            "total_payments": self._total_payments,
            "pending_orders": len(self._pending),
            "active_sessions": len(self._paid_sessions),
            "price": self.price,
        }
