"""
Thanaweya Amma Bot — Dashboard Handler
Manages the main reply keyboard and user state routing.
"""

import logging

from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from .shared import (
    SearchStates, get_main_keyboard, get_cancel_keyboard,
)

logger = logging.getLogger(__name__)

router = Router()


# ── Dashboard Button Handlers ────────────────────────────────────

@router.message(F.text == "🔍 بحث برقم الجلوس")
async def on_search_by_seat(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(SearchStates.waiting_for_seat)
    await message.answer(
        "🔢 أدخل رقم الجلوس:",
        reply_markup=get_cancel_keyboard(),
    )


@router.message(F.text == "👤 بحث بالاسم")
async def on_search_by_name(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(SearchStates.waiting_for_name)
    await message.answer(
        "📝 أدخل الاسم بالكامل:",
        reply_markup=get_cancel_keyboard(),
    )


@router.message(F.text == "ℹ️ حول")
async def on_about(message: Message) -> None:
    from ..app_state import get_search_engine
    engine = get_search_engine()
    count = engine.total_records if engine else 0

    await message.answer(
        f"🎓 <b>بوت نتيجة الثانوية العامة</b>\n\n"
        f"بوت مجاني للبحث عن نتائج الثانوية العامة المصرية.\n\n"
        f"📊 عدد السجلات المتاحة: <b>{count:,}</b>\n\n"
        f"✨ المميزات:\n"
        f"• بحث سريع برقم الجلوس\n"
        f"• بحث بالاسم الكامل\n"
        f"• توليد PDF احترافي للنتيجة\n"
        f"• دعم كامل للغة العربية\n\n"
        f"⚡ سرعة البحث: أقل من 100 مللي ثانية",
        reply_markup=get_main_keyboard(),
    )


@router.message(F.text == "❓ مساعدة")
async def on_help(message: Message) -> None:
    await message.answer(
        "📖 <b>دليل الاستخدام</b>\n\n"
        "🔍 <b>بحث برقم الجلوس:</b>\n"
        "اضغط على زر «بحث برقم الجلوس» ثم أدخل رقم الجلوس.\n"
        "سيتم إرسال نتيجة الطالب في ملف PDF.\n\n"
        "👤 <b>بحث بالاسم:</b>\n"
        "اضغط على زر «بحث بالاسم» ثم أدخل الاسم بالكامل.\n"
        "إذا وُجد أكثر من نتيجة، سيتم عرض قائمة للاختيار منها.\n\n"
        "💡 <b>نصائح:</b>\n"
        "• اكتب الاسم بالكامل للحصول على أفضل نتيجة\n"
        "• لا حاجة لكتابة التشكيل (الفتح والكسرة...)\n"
        "• يمكنك إلغاء أي بحث بالضغط على «إلغاء»\n\n"
        "🔒 البوت مجاني تماماً وبدون أي رسوم.",
        reply_markup=get_main_keyboard(),
    )


# ── Cancel & Navigation ──────────────────────────────────────────

@router.message(F.text == "❌ إلغاء")
@router.message(F.text == "🔙 القائمة الرئيسية")
async def on_cancel_or_back(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "🏠 القائمة الرئيسية",
        reply_markup=get_main_keyboard(),
    )


# ── Catch-all for unexpected text in states ──────────────────────

@router.message(StateFilter(None), F.text)
async def on_unknown_text(message: Message) -> None:
    text = message.text or ""
    if text in ["🔍 بحث برقم الجلوس", "👤 بحث بالاسم", "ℹ️ حول", "❓ مساعدة"]:
        return
    await message.answer(
        "👤 يرجى اختيار أحد الخيارات من القائمة أدناه:",
        reply_markup=get_main_keyboard(),
    )