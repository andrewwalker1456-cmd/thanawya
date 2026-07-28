"""
Thanaweya Amma Bot — Search Handler
Implements seat number and name search flows.
"""

import io
import time
import logging

from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile

from ..app_state import (
    get_config, get_search_engine, get_pdf_generator, get_stats_service,
)
from .shared import (
    SearchStates, get_main_keyboard, get_cancel_keyboard,
)

logger = logging.getLogger(__name__)

router = Router()


# ── Seat Number Search ───────────────────────────────────────────

@router.message(SearchStates.waiting_for_seat)
async def on_seat_input(message: Message, state: FSMContext) -> None:
    """Process seat number search."""
    text = (message.text or "").strip()

    # Handle cancel
    if text in ["❌ إلغاء", "🔙 القائمة الرئيسية"]:
        await state.clear()
        await message.answer("🏠 القائمة الرئيسية", reply_markup=get_main_keyboard(message))
        return

    # Validate input
    try:
        seat_number = int(text)
        if seat_number <= 0:
            raise ValueError
    except ValueError:
        await message.answer(
            "⚠️ رقم الجلوس غير صحيح.\nأدخل رقماً صحيحاً:",
            reply_markup=get_cancel_keyboard(),
        )
        return

    # Search
    start = time.time()
    engine = get_search_engine()
    stats = get_stats_service()

    if engine is None:
        await message.answer(
            "⚠️ البيانات غير محملة حالياً. يرجى المحاولة لاحقاً.",
            reply_markup=get_main_keyboard(message),
        )
        await state.clear()
        return

    record = engine.search_by_seat(seat_number)
    duration = (time.time() - start) * 1000

    stats.record_search("seat", str(seat_number), record is not None, duration)

    if record is None:
        await message.answer(
            f"❌ لم يتم العثور على نتيجة لرقم الجلوس <code>{seat_number}</code>",
            reply_markup=get_main_keyboard(message),
        )
        await state.clear()
        return

    # Generate PDF
    await state.clear()
    await _send_result_pdf(message, record, stats)


# ── Name Search ──────────────────────────────────────────────────

@router.message(SearchStates.waiting_for_name)
async def on_name_input(message: Message, state: FSMContext) -> None:
    """Process name search."""
    text = (message.text or "").strip()

    # Handle cancel
    if text in ["❌ إلغاء", "🔙 القائمة الرئيسية"]:
        await state.clear()
        await message.answer("🏠 القائمة الرئيسية", reply_markup=get_main_keyboard(message))
        return

    if len(text) < 3:
        await message.answer(
            "⚠️ الاسم قصير جداً. أدخل الاسم بالكامل:",
            reply_markup=get_cancel_keyboard(),
        )
        return

    # Search
    start = time.time()
    engine = get_search_engine()
    stats = get_stats_service()

    if engine is None:
        await message.answer(
            "⚠️ البيانات غير محملة حالياً. يرجى المحاولة لاحقاً.",
            reply_markup=get_main_keyboard(message),
        )
        await state.clear()
        return

    results = engine.search_by_name(text)
    duration = (time.time() - start) * 1000

    config = get_config()
    max_results = config.search.max_name_results

    stats.record_search("name", text, len(results) > 0, duration)

    if not results:
        await message.answer(
            f"❌ لم يتم العثور على نتائج للاسم <b>{text}</b>",
            reply_markup=get_main_keyboard(message),
        )
        await state.clear()
        return

    # Single result — generate PDF directly
    if len(results) == 1:
        await state.clear()
        await _send_result_pdf(message, results[0], stats)
        return

    # Multiple results — show selection list
    truncated = results[:max_results]
    buttons = []
    for i, record in enumerate(truncated, 1):
        buttons.append(
            [KeyboardButton(text=f"{i}. {record.name} ({record.seat_number})")]
        )

    buttons.append([KeyboardButton(text="❌ إلغاء")])

    await state.set_state(SearchStates.waiting_for_name_selection)
    await state.update_data(results=truncated, query=text)

    msg = f"📋 عُثر على <b>{len(results)}</b> نتيجة\n\nاختر الرقم المناسب:\n\n"
    for i, record in enumerate(truncated, 1):
        msg += f"<b>{i}.</b> {record.name} — رقم الجلوس: <code>{record.seat_number}</code>\n"

    if len(results) > max_results:
        msg += f"\n... و {len(results) - max_results} نتيجة أخرى"

    await message.answer(
        msg,
        reply_markup=ReplyKeyboardMarkup(
            keyboard=buttons, resize_keyboard=True,
        ),
    )


# ── Name Selection from List ─────────────────────────────────────

@router.message(SearchStates.waiting_for_name_selection)
async def on_name_selection(message: Message, state: FSMContext) -> None:
    """Handle selection from name search results."""
    text = (message.text or "").strip()

    if text in ["❌ إلغاء", "🔙 القائمة الرئيسية"]:
        await state.clear()
        await message.answer("🏠 القائمة الرئيسية", reply_markup=get_main_keyboard(message))
        return

    # Parse selection number
    try:
        selection = int(text.split(".")[0].strip())
    except ValueError:
        await message.answer(
            "⚠️ اختر رقماً من القائمة:",
            reply_markup=get_cancel_keyboard(),
        )
        return

    data = await state.get_data()
    results = data.get("results", [])

    if not (1 <= selection <= len(results)):
        await message.answer(
            f"⚠️ الرقم غير صحيح. اختر من 1 إلى {len(results)}:",
        )
        return

    record = results[selection - 1]
    await state.clear()
    stats = get_stats_service()
    await _send_result_pdf(message, record, stats)


# ── Helper: Send Result as PDF ───────────────────────────────────

async def _send_result_pdf(message: Message, record, stats_service) -> None:
    """Generate and send a PDF for the given record."""
    pdf_gen = get_pdf_generator()
    if pdf_gen is None:
        await _send_result_text(message, record)
        return

    pdf_bytes = pdf_gen.generate_pdf(record)
    if pdf_bytes is None:
        logger.error("PDF generation returned None")
        await _send_result_text(message, record)
        return

    filename = pdf_gen.generate_filename(record)

    # Summary message (HTML)
    case_emoji = _get_case_emoji(record.student_case_desc)
    summary = (
        f"✅ <b>تم العثور على النتيجة</b>\n\n"
        f"👤 الاسم: {record.name}\n"
        f"🔢 رقم الجلوس: <code>{record.seat_number}</code>\n"
        f"📊 الدرجة: <b>{record.grade:.2f}</b>\n"
        f"{case_emoji} الحالة: <b>{record.student_case_desc}</b>\n\n"
        f"📄 تم إرفاق ملف PDF بالنتيجة التفصيلية"
    )

    try:
        document = BufferedInputFile(file=pdf_bytes, filename=filename)
        await message.answer_document(
            document=document,
            caption=summary,
            reply_markup=get_main_keyboard(message),
        )
    except Exception as e:
        logger.error(f"Failed to send PDF document: {e}")
        await _send_result_text(message, record)


async def _send_result_text(message: Message, record) -> None:
    """Fallback: send result as text if PDF fails."""
    case_emoji = _get_case_emoji(record.student_case_desc)
    text = (
        f"✅ <b>النتيجة</b>\n\n"
        f"👤 الاسم: {record.name}\n"
        f"🔢 رقم الجلوس: <code>{record.seat_number}</code>\n"
        f"📊 الدرجة: <b>{record.grade:.2f}</b>\n"
        f"{case_emoji} الحالة: <b>{record.student_case_desc}</b>\n"
        f"🏷 c_flage: {record.c_flag}"
    )

    extra = record.extra_fields
    if extra:
        text += "\n\n📋 <b>بيانات إضافية:</b>\n"
        for k, v in extra.items():
            text += f"• {k}: {v}\n"

    await message.answer(text, reply_markup=get_main_keyboard(message))


def _get_case_emoji(case_desc: str) -> str:
    """Return emoji based on student case."""
    if not case_desc:
        return "❓"
    desc = case_desc.strip()
    if "ناجح" in desc:
        return "🎉"
    if "راسب" in desc:
        return "😔"
    if "غياب" in desc:
        return "⚠️"
    if "دور ثان" in desc:
        return "🔄"
    return "📋"