"""
Thanaweya Amma Bot — Search Handler
Implements seat number and name search flows.
"""

import io
import time
import logging

from aiogram import Router, F
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, BufferedInputFile
)
from aiogram.fsm.context import FSMContext

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
    results_data = [{"seat": r.seat_number, "name": r.name} for r in results]
    await state.set_state(SearchStates.waiting_for_name_selection)
    await state.update_data(results=results_data, query=text, current_page=0)

    items_per_page = 5
    total_pages = (len(results) + items_per_page - 1) // items_per_page

    msg = f"🔍 <b>نتائج البحث عن:</b> \"{text}\"\n"
    msg += f"📊 إجمالي النتائج: <b>{len(results)}</b>\n\n"
    msg += "الرجاء اختيار الاسم المطلوب من القائمة أدناه:\n\n"

    for i, r in enumerate(results[:items_per_page], 1):
        msg += f"<b>{i}.</b> {r.name} — رقم الجلوس: <code>{r.seat_number}</code>\n"

    # Send the first page with inline keyboard
    await message.answer(
        msg,
        reply_markup=_get_search_pagination_keyboard(results_data, 0, total_pages),
        parse_mode="HTML"
    )


# ── Name Selection & Pagination Callbacks ─────────────────────────

def _get_search_pagination_keyboard(results: list, page: int, total_pages: int, items_per_page: int = 5) -> InlineKeyboardMarkup:
    """Build inline keyboard for search pagination."""
    keyboard_buttons = []
    
    start_idx = page * items_per_page
    end_idx = min(start_idx + items_per_page, len(results))
    page_results = results[start_idx:end_idx]
    
    # 1. Names Buttons
    for i, r in enumerate(page_results, start_idx + 1):
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"{i}. {r['name']} ({r['seat']})",
                callback_data=f"name_sel:{r['seat']}"
            )
        ])
        
    # 2. Pagination Nav Row
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="◀️ السابق", callback_data=f"name_page:{page-1}"))
    
    nav_row.append(InlineKeyboardButton(text=f"📄 {page+1} / {total_pages}", callback_data="name_noop"))
    
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="التالي ▶️", callback_data=f"name_page:{page+1}"))
        
    keyboard_buttons.append(nav_row)
    
    # 3. Cancel Button Row
    keyboard_buttons.append([
        InlineKeyboardButton(text="❌ إلغاء", callback_data="name_cancel")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)


@router.callback_query(F.data.startswith("name_page:"))
async def on_name_page_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle page switching clicks."""
    data = await state.get_data()
    results = data.get("results", [])
    query = data.get("query", "")
    if not results:
        await callback.answer("⚠️ انتهت صلاحية جلسة البحث. يرجى البحث مجدداً.", show_alert=True)
        return
        
    target_page = int(callback.data.split(":")[1])
    items_per_page = 5
    total_pages = (len(results) + items_per_page - 1) // items_per_page
    
    await state.update_data(current_page=target_page)
    
    start_idx = target_page * items_per_page
    end_idx = min(start_idx + items_per_page, len(results))
    page_results = results[start_idx:end_idx]
    
    msg = f"🔍 <b>نتائج البحث عن:</b> \"{query}\"\n"
    msg += f"📊 إجمالي النتائج: <b>{len(results)}</b>\n\n"
    msg += "الرجاء اختيار الاسم المطلوب من القائمة أدناه:\n\n"
    
    for i, r in enumerate(page_results, start_idx + 1):
        msg += f"<b>{i}.</b> {r['name']} — رقم الجلوس: <code>{r['seat']}</code>\n"
        
    await callback.message.edit_text(
        text=msg,
        reply_markup=_get_search_pagination_keyboard(results, target_page, total_pages),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("name_sel:"))
async def on_name_select_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle student name selection from the list."""
    seat_number = int(callback.data.split(":")[1])
    await state.clear()
    
    try:
        await callback.message.delete()
    except Exception:
        pass
        
    engine = get_search_engine()
    record = engine.search_by_seat(seat_number)
    if not record:
        await callback.message.answer("❌ لم يتم العثور على هذا الطالب في قاعدة البيانات.")
        return
        
    stats = get_stats_service()
    await _send_result_pdf(callback.message, record, stats)
    await callback.answer()


@router.callback_query(F.data == "name_cancel")
async def on_name_cancel_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle cancel click on inline list."""
    await state.clear()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer("🏠 القائمة الرئيسية", reply_markup=get_main_keyboard(callback.message))
    await callback.answer()


@router.callback_query(F.data == "name_noop")
async def on_name_noop(callback: CallbackQuery) -> None:
    """No-op callback for middle page count indicator."""
    await callback.answer()


@router.message(SearchStates.waiting_for_name_selection)
async def on_name_selection_text(message: Message, state: FSMContext) -> None:
    """Fallback text handler in case they type something or click cancel on ReplyKeyboard."""
    text = (message.text or "").strip()
    if text in ["❌ إلغاء", "🔙 القائمة الرئيسية"]:
        await state.clear()
        await message.answer("🏠 القائمة الرئيسية", reply_markup=get_main_keyboard(message))
        return
        
    await message.answer(
        "⚠️ <b>الرجاء اختيار الاسم المطلوب بالضغط على الأزرار المرفقة بقائمة النتائج أعلاه</b>، أو اضغط على <b>❌ إلغاء</b> للعودة.",
        parse_mode="HTML"
    )


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
    grade = getattr(record, 'grade', 0.0) or 0.0
    percentage = (grade / 320.0) * 100
    summary = (
        f"✅ <b>تم العثور على النتيجة</b>\n\n"
        f"👤 الاسم: {record.name}\n"
        f"🔢 رقم الجلوس: <code>{record.seat_number}</code>\n"
        f"📊 الدرجة: <b>{grade:.2f}</b> (<b>{percentage:.2f}%</b>)\n"
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
    grade = getattr(record, 'grade', 0.0) or 0.0
    percentage = (grade / 320.0) * 100
    text = (
        f"✅ <b>النتيجة</b>\n\n"
        f"👤 الاسم: {record.name}\n"
        f"🔢 رقم الجلوس: <code>{record.seat_number}</code>\n"
        f"📊 الدرجة: <b>{grade:.2f}</b> (<b>{percentage:.2f}%</b>)\n"
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