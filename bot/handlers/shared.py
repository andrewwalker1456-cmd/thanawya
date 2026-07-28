"""
Thanaweya Amma Bot — Shared UI Components
Keyboard builders and FSM states used across handlers.
"""

from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


# ── FSM States ───────────────────────────────────────────────────

class SearchStates(StatesGroup):
    """FSM states for search flows."""
    waiting_for_seat = State()
    waiting_for_name = State()
    waiting_for_name_selection = State()


class AdminStates(StatesGroup):
    """FSM states for admin flows."""
    waiting_for_upload = State()
    waiting_for_confirmation = State()
    waiting_for_broadcast = State()
    waiting_for_ban = State()
    waiting_for_unban = State()
    waiting_for_search_user = State()


# ── Keyboard Builders ────────────────────────────────────────────

def get_main_keyboard(event = None) -> ReplyKeyboardMarkup:
    """Build the always-visible main dashboard keyboard, adding Admin Panel if user is admin."""
    is_admin = False
    if event:
        from ..app_state import get_config
        config = get_config()
        user = getattr(event, "from_user", None)
        uid = user.id if user else 0
        is_admin = uid in config.bot.admin_ids

    keyboard_layout = [
        [
            KeyboardButton(text="🔍 بحث برقم الجلوس"),
            KeyboardButton(text="👤 بحث بالاسم"),
        ],
        [
            KeyboardButton(text="📞 الدعم"),
            KeyboardButton(text="ℹ️ حول"),
            KeyboardButton(text="❓ مساعدة"),
        ],
    ]

    if is_admin:
        keyboard_layout.append([KeyboardButton(text="🔧 لوحة التحكم")])

    return ReplyKeyboardMarkup(
        keyboard=keyboard_layout,
        resize_keyboard=True,
        input_field_placeholder="اختر من القائمة...",
    )


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Keyboard with cancel button during flows."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❌ إلغاء")],
        ],
        resize_keyboard=True,
    )


def get_back_keyboard() -> ReplyKeyboardMarkup:
    """Keyboard with back to menu button."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔙 القائمة الرئيسية")],
        ],
        resize_keyboard=True,
    )