"""
Thanaweya Amma Bot — Payment Handler
Handles payment creation, confirmation, and preauth for search access.
"""

import logging

from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext

from ..app_state import get_config, get_payment_service, get_search_engine, get_pdf_generator, get_stats_service
from .shared import get_main_keyboard, get_cancel_keyboard, SearchStates

logger = logging.getLogger(__name__)

router = Router()


async def require_payment(message: Message, state: FSMContext,
                            search_type: str, search_query: str) -> bool:
    """
    Check if payment is required. Returns True if access is granted.
    If payment is needed, sends payment prompt and returns False.
    Called from search handlers before performing the actual search.
    """
    config = get_config()
    pay_svc = get_payment_service()
    user_id = message.from_user.id

    # Payment disabled — allow all
    if not config.payment.enabled or pay_svc is None:
        return True

    # Admin bypass
    if pay_svc.is_admin_bypass(user_id, config.bot.admin_ids):
        return True

    # Already has active paid session
    if pay_svc.has_paid_session(user_id):
        return True

    # Payment required — create order and send link
    await _send_payment_prompt(message, state, pay_svc, user_id,
                                search_type, search_query)
    return False


async def _send_payment_prompt(message: Message, state: FSMContext,
                                pay_svc, user_id: int,
                                search_type: str, search_query: str):
    """Create payment order and send the payment link to user."""
    await state.set_state(SearchStates.waiting_for_payment)
    await state.update_data(
        search_type=search_type,
        search_query=search_query,
    )

    # Create payment
    user_payment = await pay_svc.create_payment(
        user_id=user_id,
        search_type=search_type,
        search_query=search_query,
    )

    order = user_payment.order

    # Build message
    text = (
        f"💰 <b>الدفع مطلوب</b>\n\n"
        f"للبحث عن النتيجة يرجى دفع مبلغ <b>{order.amount:.0f} جنيه</b>\n\n"
        f"🔢 رقم الطلب: <code>{order.order_id}</code>\n\n"
        f"اضغط على زر الدفع أدناه، وبعد إتمام الدفع "
        f"اضغط \"✅ تم الدفع\""
    )

    buttons = []
    if order.payment_url:
        buttons.append([InlineKeyboardButton(
            text=f"💳 دفع {order.amount:.0f} جنيه",
            url=order.payment_url,
        )])
    buttons.append([InlineKeyboardButton(
        text="✅ تم الدفع",
        callback_data=f"pay_confirm_{order.order_id}",
    )])
    buttons.append([InlineKeyboardButton(
        text="❌ إلغاء",
        callback_data="pay_cancel",
    )])

    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(F.data.startswith("pay_confirm_"))
async def on_payment_confirm(callback: CallbackQuery):
    """User clicked 'payment confirmed' — verify with AmmerPay then auto-execute search."""
    order_id = callback.data.replace("pay_confirm_", "")
    pay_svc = get_payment_service()

    if not pay_svc:
        await callback.answer("❌ نظام الدفع غير متاح", show_alert=True)
        return

    # Check payment status
    confirmed = await pay_svc.confirm_payment(order_id)

    if confirmed:
        await callback.answer("✅ تم تأكيد الدفع!", show_alert=True)

        # Get the saved search query from FSM state
        from aiogram.fsm.storage.memory import MemoryStorage

        # Retrieve saved search data
        data = await callback.bot.get_current_state().get_data()
        # Try to get from callback's user state
        try:
            state_data = await callback.state.get_data()
        except Exception:
            state_data = {}

        search_type = state_data.get("search_type", "")
        search_query = state_data.get("search_query", "")

        # Delete the payment message
        try:
            await callback.message.delete()
        except Exception:
            pass

        # If we have saved search context, auto-execute it
        if search_query:
            await _execute_search_after_payment(
                callback, pay_svc, search_type, search_query
            )
        else:
            await callback.message.answer(
                "✅ <b>تم تأكيد الدفع بنجاح!</b>\n\n"
                "يمكنك الآن البحث عن النتيجة."
                "اختر نوع البحث من القائمة:",
                reply_markup=get_main_keyboard(),
            )
    else:
        await callback.answer(
            "⏳ لم يتم العثور على الدفع بعد."
            " تأكد من إتمام عملية الدفع ثم حاول مرة أخرى.",
            show_alert=True,
        )


async def _execute_search_after_payment(
    callback: CallbackQuery, pay_svc, search_type: str, search_query: str
):
    """After payment confirmed, auto-execute the saved search."""
    import time
    engine = get_search_engine()
    stats = get_stats_service()

    if engine is None:
        await callback.message.answer(
            "⚠️ البيانات غير محملة حالياً. يرجى المحاولة لاحقاً.",
            reply_markup=get_main_keyboard(),
        )
        return

    start = time.time()

    if search_type == "seat":
        try:
            seat_number = int(search_query)
            record = engine.search_by_seat(seat_number)
        except ValueError:
            await callback.message.answer(
                "⚠️ رقم الجلوس غير صحيح.",
                reply_markup=get_main_keyboard(),
            )
            return

        duration = (time.time() - start) * 1000
        stats.record_search("seat", search_query, record is not None, duration)

        if record is None:
            await callback.message.answer(
                f"❌ لم يتم العثور على نتيجة لرقم الجلوس <code>{search_query}</code>",
                reply_markup=get_main_keyboard(),
            )
            return

        # Send PDF
        await _send_result_pdf_to_chat(callback, record, stats)

    elif search_type == "name":
        results = engine.search_by_name(search_query)
        duration = (time.time() - start) * 1000

        config = get_config()
        max_results = config.search.max_name_results
        stats.record_search("name", search_query, len(results) > 0, duration)

        if not results:
            await callback.message.answer(
                f"❌ لم يتم العثور على نتائج للاسم <b>{search_query}</b>",
                reply_markup=get_main_keyboard(),
            )
            return

        # Single result — generate PDF directly
        if len(results) == 1:
            await _send_result_pdf_to_chat(callback, results[0], stats)
            return

        # Multiple results — tell user to search again (now with paid session)
        msg = f"✅ <b>تم الدفع بنجاح!</b>\n\n"
        msg += f"عُثر على <b>{len(results)}</b> نتيجة للاسم <b>{search_query}</b>\n\n"
        msg += "اختر نوع البحث من القائمة مرة أخرى لعرض النتائج:"
        await callback.message.answer(msg, reply_markup=get_main_keyboard())

    else:
        await callback.message.answer(
            "✅ <b>تم تأكيد الدفع بنجاح!</b>\n"
            "اختر نوع البحث من القائمة:",
            reply_markup=get_main_keyboard(),
        )


async def _send_result_pdf_to_chat(callback: CallbackQuery, record, stats_service) -> None:
    """Generate and send a PDF for the given record via callback message."""
    from aiogram.types import BufferedInputFile

    pdf_gen = get_pdf_generator()
    if pdf_gen is None:
        await _send_result_text_to_chat(callback, record)
        return

    pdf_bytes = pdf_gen.generate_pdf(record)
    if pdf_bytes is None:
        logger.error("PDF generation returned None")
        await _send_result_text_to_chat(callback, record)
        return

    filename = pdf_gen.generate_filename(record)
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
        await callback.message.answer_document(
            document=document,
            caption=summary,
            reply_markup=get_main_keyboard(),
        )
    except Exception as e:
        logger.error(f"Failed to send PDF document: {e}")
        await _send_result_text_to_chat(callback, record)


async def _send_result_text_to_chat(callback: CallbackQuery, record) -> None:
    """Fallback: send result as text if PDF fails."""
    case_emoji = _get_case_emoji(record.student_case_desc)
    text = (
        f"✅ <b>النتيجة</b>\n\n"
        f"👤 الاسم: {record.name}\n"
        f"🔢 رقم الجلوس: <code>{record.seat_number}</code>\n"
        f"📊 الدرجة: <b>{record.grade:.2f}</b>\n"
        f"{case_emoji} الحالة: {record.student_case_desc}\n"
        f"🏷 c_flage: {record.c_flag}"
    )
    extra = record.extra_fields
    if extra:
        text += "\n\n📋 <b>بيانات إضافية:</b>\n"
        for k, v in extra.items():
            text += f"• {k}: {v}\n"
    await callback.message.answer(text, reply_markup=get_main_keyboard())


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


@router.callback_query(F.data == "pay_cancel")
async def on_payment_cancel(callback: CallbackQuery):
    """User cancelled payment."""
    await callback.message.delete()
    await callback.message.answer(
        "🏠 القائمة الرئيسية",
        reply_markup=get_main_keyboard(),
    )
