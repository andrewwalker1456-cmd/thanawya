import logging
import hashlib
import time
import json
import aiohttp
from typing import Optional, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PaymentOrder:
    """Represents a payment order."""
    order_id: str
    amount: float
    currency: str
    payment_url: Optional[str] = None
    status: str = "pending"
    created_at: float = 0.0
    paid_at: Optional[float] = None
    provider_order_id: Optional[str] = None
    user_id: Optional[int] = None


class AmmerPayClient:
    """Client for AmmerPay payment gateway.

    Key format: APP_ID:MODE:SECRET
    The TG_ prefix in the secret indicates Telegram-native integration.
    """

    BASE_URL = "https://ammerpay.com/api/v1"

    def __init__(self, api_key: str):
        parts = api_key.split(":")
        self.app_id = parts[0]
        self.mode = parts[1] if len(parts) > 1 else "LIVE"
        self.secret = parts[2] if len(parts) > 2 else parts[1]
        self.api_key = api_key
        self.is_test = self.mode == "TEST"

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def create_order(
        self,
        amount: float,
        currency: str = "EGP",
        order_id: str = "",
        description: str = "",
        user_id: Optional[int] = None,
        callback_url: Optional[str] = None,
    ) -> PaymentOrder:
        if not order_id:
            order_id = f"{int(time.time())}_{user_id or 0}"

        payload = {
            "app_id": int(self.app_id),
            "order_id": order_id,
            "amount": amount,
            "currency": currency,
            "description": description or "Thanaweya Results Search",
            "callback_url": callback_url,
            "metadata": {"telegram_user_id": user_id},
        }

        order = PaymentOrder(
            order_id=order_id,
            amount=amount,
            currency=currency,
            user_id=user_id,
            created_at=time.time(),
        )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.BASE_URL}/order/create",
                    headers=self._headers(),
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status in (200, 201):
                        data = await resp.json()
                        order.payment_url = (
                            data.get("payment_url")
                            or data.get("checkout_url")
                            or data.get("url")
                        )
                        order.provider_order_id = data.get("id") or data.get("order_id")
                        logger.info(f"AmmerPay order created: {order_id}")
                    else:
                        body = await resp.text()
                        logger.warning(f"AmmerPay {resp.status}: {body[:200]}")
                        # Fallback payment URL
                        order.payment_url = (
                            f"https://ammerpay.com/pay/{self.app_id}"
                            f"?order={order_id}&amount={amount}"
                        )
        except Exception as e:
            logger.warning(f"AmmerPay API failed: {e}, using fallback URL")
            order.payment_url = (
                f"https://ammerpay.com/pay/{self.app_id}"
                f"?order={order_id}&amount={amount}"
            )

        return order

    async def check_status(self, order_id: str) -> str:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.BASE_URL}/order/status",
                    headers=self._headers(),
                    params={"order_id": order_id},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("status", "unknown")
        except Exception as e:
            logger.warning(f"AmmerPay status check failed: {e}")
        return "unknown"

    def verify_callback(self, data: Dict[str, Any], signature: str) -> bool:
        expected = hashlib.sha256(
            f"{json.dumps(data, sort_keys=True)}{self.secret}".encode()
        ).hexdigest()
        return expected == signature
