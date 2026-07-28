"""
Thanaweya Amma Bot — Admin Handler
Admin panel: file upload, statistics, system management.
"""

import logging
import os
import sys
import asyncio
from pathlib import Path

from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton, Document,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, BufferedInputFile
)
from aiogram.fsm.context import FSMContext

from ..app_state import (
    get_config, get_search_engine, get_importer, get_stats_service,
)
from .shared import AdminStates, get_main_keyboard, get_cancel_keyboard

logger = logging.getLogger(__name__)

router = Router()


def is_admin(message: Message) -> bool:
    config = get_config()
    user_id = message.from_user.id if message.from_user else 0
    return user_id in config.bot.admin_ids


def get_admin_keyboard() -> ReplyKeyboardMarkup:
    """Build the admin dashboard keyboard."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📤 رفع ملف جديد"),
                KeyboardButton(text="📊 الإحصائيات"),
            ],
            [
                KeyboardButton(text="📢 إرسال جماعي"),
                KeyboardButton(text="👥 المشتركون"),
            ],
            [
                KeyboardButton(text="🚫 إدارة الحظر"),
                KeyboardButton(text="📥 تصدير المشتركين"),
            ],
            [
                KeyboardButton(text="🔍 استعلام عن مستخدم"),
                KeyboardButton(text="🩺 صحة النظام"),
            ],
            [
                KeyboardButton(text="📜 سجل الأخطاء"),
                KeyboardButton(text="🔙 القائمة الرئيسية"),
            ],
        ],
        resize_keyboard=True,
    )


# ── Admin Entry Point ────────────────────────────────────────────

@router.message(F.text == "/admin")
async def on_admin_entry(message: Message) -> None:
    if not is_admin(message):
        return

    await message.answer(
        "🔧 <b>لوحة تحكم المسؤول</b>\n\nاختر أحد الخيارات:",
        reply_markup=get_admin_keyboard(),
    )


# ── Upload New File ──────────────────────────────────────────────

@router.message(F.text == "📤 رفع ملف جديد")
async def on_upload_prompt(message: Message, state: FSMContext) -> None:
    if not is_admin(message):
        return

    config = get_config()
    max_mb = config.admin.max_upload_size_mb

    await state.set_state(AdminStates.waiting_for_upload)
    await message.answer(
        f"📤 أرسل ملف Excel (.xlsx)\n"
        f"📏 الحد الأقصى: {max_mb} MB\n\n"
        f"⚠️ سيتم استبدال البيانات الحالية بالبيانات الجديدة.",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="❌ إلغاء")]],
            resize_keyboard=True,
        ),
    )


@router.message(AdminStates.waiting_for_upload, F.document)
async def on_upload_file(message: Message, state: FSMContext) -> None:
    if not is_admin(message):
        return

    config = get_config()
    importer = get_importer()
    if importer is None:
        await message.answer("❌ النظام غير جاهز حالياً.")
        await state.clear()
        return

    doc: Document = message.document
    max_bytes = config.admin.max_upload_size_mb * 1024 * 1024

    if doc.file_size and doc.file_size > max_bytes:
        await message.answer(
            f"❌ حجم الملف كبير جداً ({doc.file_size / 1024 / 1024:.1f} MB).\n"
            f"الحد الأقصى: {config.admin.max_upload_size_mb} MB"
        )
        return

    filename = doc.file_name or ""
    if not filename.lower().endswith(".xlsx"):
        await message.answer("❌ يجب أن يكون الملف بصيغة .xlsx")
        return

    await message.answer("⏳ جاري تحميل الملف...")
    try:
        upload_dir = Path(config.data.upload_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)

        filepath = upload_dir / filename
        await message.bot.download(file=doc, destination=filepath)

        await state.clear()
        await message.answer("⏳ جاري استيراد البيانات وبناء الفهارس...\nقد يستغرق هذا بضع دقائق.")

        try:
            _, stats = get_importer().import_file(filepath)
            stats_service = get_stats_service()
            stats_service.record_import({
                "file_path": str(filepath),
                "valid_rows": stats.valid_rows if stats else 0,
                "duplicate_seats": stats.duplicate_seats if stats else 0,
                "import_time_seconds": stats.import_time_seconds if stats else 0,
            })

            if stats and stats.error:
                await message.answer(
                    f"❌ فشل الاستيراد:\n{stats.error}",
                    reply_markup=get_main_keyboard(),
                )
            else:
                await message.answer(
                    f"✅ <b>تم الاستيراد بنجاح!</b>\n\n"
                    f"📊 السجلات: <b>{stats.valid_rows:,}</b> "
                    f"(من أصل <b>{stats.total_rows:,}</b>)\n"
                    f"🔄 المكررات: <b>{stats.duplicate_seats:,}</b>\n"
                    f"⏱ الوقت: <b>{stats.import_time_seconds:.1f}</b> ثانية",
                    reply_markup=get_main_keyboard(),
                )
        except Exception as e:
            logger.error(f"Import failed: {e}", exc_info=True)
            get_stats_service().record_error(f"Import failed: {e}")
            await message.answer(
                f"❌ فشل الاستيراد: {e}",
                reply_markup=get_main_keyboard(),
            )

    except Exception as e:
        logger.error(f"Upload processing failed: {e}", exc_info=True)
        await message.answer(
            f"❌ حدث خطأ أثناء معالجة الملف: {e}",
            reply_markup=get_main_keyboard(),
        )
        await state.clear()


# ── Statistics Dashboard ─────────────────────────────────────────

@router.message(F.text == "📊 الإحصائيات")
async def on_stats(message: Message) -> None:
    if not is_admin(message):
        return

    stats_service = get_stats_service()
    stats = stats_service.get_stats()
    engine = get_search_engine()

    engine_stats = engine.get_stats() if engine else {"total_records": 0}
    sys_info = stats.get("system", {})

    text = (
        "📊 <b>إحصائيات النظام</b>\n\n"
        f"📦 إجمالي السجلات: <b>{engine_stats.get('total_records', 0):,}</b>\n"
        f"🔤 الأسماء الفريدة: <b>{engine_stats.get('unique_names', 0):,}</b>\n"
        f"📑 البطاقات الفريدة: <b>{engine_stats.get('unique_tokens', 0):,}</b>\n\n"
        f"🔍 <b>عمليات البحث:</b>\n"
        f"  • الإجمالي: <b>{stats['total_searches']:,}</b>\n"
        f"  • اليوم: <b>{stats['today_searches']:,}</b>\n"
        f"  • برقم الجلوس: <b>{stats['seat_searches']:,}</b>\n"
        f"  • بالاسم: <b>{stats['name_searches']:,}</b>\n"
        f"  • ناجحة: <b>{stats['successful_searches']:,}</b>\n"
        f"  • فاشلة: <b>{stats['failed_searches']:,}</b>\n"
        f"  • متوسط الزمن: <b>{stats['avg_search_time_ms']:.2f}</b> مللي ثانية\n\n"
        f"💻 <b>النظام:</b>\n"
        f"  • الذاكرة: <b>{sys_info.get('memory_mb', 0):.1f}</b> MB\n"
        f"  • وقت التشغيل: <b>{int(sys_info.get('uptime_seconds', 0) // 3600)}</b> ساعة"
    )

    top_seats = stats.get("top_searched_seats", [])[:5]
    if top_seats:
        text += "\n\n🔢 <b>الأكثر بحثاً (أرقام الجلوس):</b>\n"
        for seat, count in top_seats:
            text += f"  • <code>{seat}</code> — {count} مرة\n"

    top_names = stats.get("top_searched_names", [])[:5]
    if top_names:
        text += "\n👤 <b>الأكثر بحثاً (أسماء):</b>\n"
        for name, count in top_names:
            text += f"  • {name} — {count} مرة\n"

    await message.answer(text)


# ── System Health ────────────────────────────────────────────────

@router.message(F.text == "🩺 صحة النظام")
async def on_health(message: Message) -> None:
    if not is_admin(message):
        return

    import psutil
    process = psutil.Process()

    engine = get_search_engine()
    importer = get_importer()

    import_stats = importer.last_import_stats if importer else None

    running = "يعمل" if (engine and engine.is_loaded()) else "غير متصل"
    text = (
        "🩺 <b>صحة النظام</b>\n\n"
        f"🟢 الحالة: <b>{running}</b>\n\n"
        f"💾 <b>الموارد:</b>\n"
        f"  • ذاكرة العملية: <b>{process.memory_info().rss / 1024 / 1024:.1f}</b> MB\n"
        f"  • ذاكرة النظام: <b>{psutil.virtual_memory().percent}%</b>\n"
        f"  • CPU: <b>{psutil.cpu_percent()}%</b>\n\n"
    )

    if import_stats:
        fname = import_stats.file_path.split('/')[-1] if import_stats.file_path else 'N/A'
        text += (
            f"📦 <b>آخر استيراد:</b>\n"
            f"  • الملف: <code>{fname}</code>\n"
            f"  • السجلات: <b>{import_stats.valid_rows:,}</b>\n"
            f"  • المكررات: <b>{import_stats.duplicate_seats:,}</b>\n"
            f"  • الوقت: <b>{import_stats.import_time_seconds:.1f}</b> ثانية\n"
            f"  • الأعمدة: {', '.join(import_stats.columns[:5])}\n"
        )

    await message.answer(text)


# ── Error Log ────────────────────────────────────────────────────

@router.message(F.text == "📜 سجل الأخطاء")
async def on_error_log(message: Message) -> None:
    if not is_admin(message):
        return

    stats_service = get_stats_service()
    stats = stats_service.get_stats()
    errors = stats.get("recent_errors", [])

    if not errors:
        await message.answer("✅ لا توجد أخطاء مسجلة مؤخراً.")
        return

    text = "📜 <b>آخر الأخطاء</b> (آخر 20):\n\n"
    for err in errors[-15:]:
        err_time = err.get("time", "")[:19]
        err_msg = err.get("error", "")[:100]
        text += f"⏱ <code>{err_time}</code>\n❌ {err_msg}\n\n"

    await message.answer(text)


# ── Re-import ────────────────────────────────────────────────────

@router.message(F.text == "🔄 إعادة استيراد")
async def on_reimport(message: Message) -> None:
    if not is_admin(message):
        return

    config = get_config()

    upload_dir = Path(config.data.upload_dir)
    xlsx_files = sorted(upload_dir.glob("*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True)

    if not xlsx_files:
        await message.answer("❌ لا توجد ملفات محملة لإعادة استيرادها.")
        return

    latest = xlsx_files[0]
    await message.answer(f"⏳ جاري إعادة استيراد: {latest.name}...")

    try:
        _, stats = get_importer().import_file(latest)
        if stats and not stats.error:
            await message.answer(
                f"✅ تم إعادة الاستيراد بنجاح!\n"
                f"📊 <b>{stats.valid_rows:,}</b> سجل في <b>{stats.import_time_seconds:.1f}</b> ثانية"
            )
        else:
            await message.answer(f"❌ فشلت إعادة الاستيراد: {stats.error if stats else 'Unknown'}")
    except Exception as e:
        await message.answer(f"❌ خطأ: {e}")


# ── Cancel in admin states ───────────────────────────────────────

@router.message(StateFilter(AdminStates), F.text == "❌ إلغاء")
async def on_admin_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("🏠 لوحة التحكم", reply_markup=get_admin_keyboard())


@router.message(F.text == "👥 المشتركون")
async def on_subscribers_list(message: Message) -> None:
    if not is_admin(message):
        return

    from ..services.user_service import get_subscribed_users
    users = get_subscribed_users()
    
    if not users:
        await message.answer("👥 لا يوجد مستخدمون مشتركون حالياً.")
        return
        
    total_count = len(users)
    recent_users = users[:50]  # Limit to 50 for message size limits
    
    text = f"👥 <b>قائمة المشتركين النشطين</b>\n"
    text += f"📊 إجمالي المشتركين: <b>{total_count:,}</b>\n"
    if total_count > 50:
        text += f"🔍 يعرض آخر 50 مشتركاً:\n\n"
    else:
        text += f"\n"
        
    for i, u in enumerate(recent_users, 1):
        uid, uname, fname, lname, last_seen = u
        name = f"{fname or ''} {lname or ''}".strip() or "مستخدم بدون اسم"
        username_str = f" (@{uname})" if uname else ""
        text += f"{i}. <b>{name}</b>{username_str}\n   └ ID: <code>{uid}</code> | ⏱ {last_seen[:16]}\n"
        
    await message.answer(text, parse_mode="HTML")


# ── Broadcast Message / Polls ────────────────────────────────────

@router.message(F.text == "📢 إرسال جماعي")
async def on_broadcast_prompt(message: Message, state: FSMContext) -> None:
    if not is_admin(message):
        return
        
    await state.set_state(AdminStates.waiting_for_broadcast)
    await message.answer(
        "📢 <b>أرسل الرسالة التي تريد بثها للمشتركين:</b>\n"
        "يمكن أن تكون نصاً، صورة، فيديو، أو استفتاء (Poll).\n\n"
        "<i>سيتم إرسالها كما هي لجميع المستخدمين المشتركين غير المحظورين.</i>",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )


@router.message(AdminStates.waiting_for_broadcast)
async def on_broadcast_execute(message: Message, state: FSMContext) -> None:
    if not is_admin(message):
        return
        
    await state.clear()
    
    from ..services.user_service import get_subscribed_users, set_subscription_status
    users = get_subscribed_users()
    
    if not users:
        await message.answer("❌ لا يوجد مستخدمون نشطون لإرسال الرسالة لهم.", reply_markup=get_admin_keyboard())
        return
        
    progress_msg = await message.answer("⏳ جاري بدء الإرسال الجماعي...")
    
    success = 0
    failed = 0
    
    for u in users:
        uid = u[0]
        try:
            # Copy the message (preserves formatting, media, polls)
            await message.copy_to(chat_id=uid)
            success += 1
            await asyncio.sleep(0.05)  # Telegram rate limit safety
        except Exception as e:
            logger.warning(f"Failed to send broadcast to {uid}: {e}")
            failed += 1
            # Auto-unsub user if they blocked the bot
            if "blocked" in str(e).lower() or "deactivated" in str(e).lower() or "chat not found" in str(e).lower():
                set_subscription_status(uid, False)
                
    try:
        await progress_msg.delete()
    except Exception:
        pass
    
    await message.answer(
        f"📢 <b>اكتمل الإرسال الجماعي!</b>\n\n"
        f"✅ تم الإرسال بنجاح: <b>{success:,}</b> مستخدم\n"
        f"❌ فشل الإرسال: <b>{failed:,}</b> مستخدم",
        reply_markup=get_admin_keyboard(),
        parse_mode="HTML"
    )


# ── Export Subscribers to Excel ──────────────────────────────────

@router.message(F.text == "📥 تصدير المشتركين")
async def on_export_subscribers(message: Message) -> None:
    if not is_admin(message):
        return

    await message.answer("⏳ جاري استخراج البيانات وإنشاء ملف Excel...")
    
    from ..services.user_service import get_all_users
    users = get_all_users()
    
    if not users:
        await message.answer("❌ لا يوجد مستخدمون لتصديرهم.", reply_markup=get_admin_keyboard())
        return
        
    try:
        import openpyxl
        from io import BytesIO
        
        # Create Excel
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "المشتركون"
        
        # Headers
        headers = ["User ID", "Username", "First Name", "Last Name", "Subscribed", "Banned", "Last Seen"]
        ws.append(headers)
        
        for u in users:
            ws.append(list(u))
            
        # Format columns width
        for col in ws.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = openpyxl.utils.get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 3, 10)
            
        # Save to memory stream
        file_stream = BytesIO()
        wb.save(file_stream)
        file_stream.seek(0)
        
        input_file = BufferedInputFile(file_stream.read(), filename="subscribers.xlsx")
        await message.answer_document(
            document=input_file,
            caption=f"✅ تم تصدير <b>{len(users)}</b> مستخدم بنجاح.",
            reply_markup=get_admin_keyboard(),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to export subscribers: {e}", exc_info=True)
        await message.answer(f"❌ حدث خطأ أثناء التصدير: {e}", reply_markup=get_admin_keyboard())


# ── Ban Management ───────────────────────────────────────────────

@router.message(F.text == "🚫 إدارة الحظر")
async def on_ban_management(message: Message) -> None:
    if not is_admin(message):
        return
        
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🚫 حظر مستخدم", callback_data="admin_ban"),
            InlineKeyboardButton(text="🔓 إلغاء الحظر", callback_data="admin_unban")
        ]
    ])
    
    await message.answer(
        "🚫 <b>لوحة إدارة الحظر</b>\n\nاختر العملية التي تريد القيام بها:", 
        reply_markup=keyboard, 
        parse_mode="HTML"
    )


@router.callback_query(F.data == "admin_ban")
async def on_ban_click(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(AdminStates.waiting_for_ban)
    await callback.message.answer(
        "🚫 <b>أدخل معرف المستخدم (User ID) أو يوزره (مثل @username) لحظره:</b>",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "admin_unban")
async def on_unban_click(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(AdminStates.waiting_for_unban)
    await callback.message.answer(
        "🔓 <b>أدخل معرف المستخدم (User ID) أو يوزره (مثل @username) لإلغاء حظره:</b>",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )


@router.message(AdminStates.waiting_for_ban, F.text)
async def on_ban_execute(message: Message, state: FSMContext) -> None:
    if not is_admin(message):
        return
        
    query = message.text.strip()
    from ..services.user_service import search_user, ban_user
    
    user = search_user(query)
    if not user:
        await message.answer(f"❌ لم يتم العثور على المستخدم '{query}' في قاعدة البيانات.")
        return
        
    uid, uname, fname, lname, _, _, _ = user
    ban_user(uid)
    
    name = f"{fname or ''} {lname or ''}".strip() or "بدون اسم"
    await message.answer(
        f"✅ <b>تم حظر المستخدم بنجاح!</b>\n\n"
        f"👤 الاسم: <b>{name}</b>\n"
        f"🆔 المعرف: <code>{uid}</code>\n"
        f"🏷 اليوزر: @{uname or 'لا يوجد'}",
        reply_markup=get_admin_keyboard(),
        parse_mode="HTML"
    )
    await state.clear()


@router.message(AdminStates.waiting_for_unban, F.text)
async def on_unban_execute(message: Message, state: FSMContext) -> None:
    if not is_admin(message):
        return
        
    query = message.text.strip()
    from ..services.user_service import search_user, unban_user
    
    user = search_user(query)
    if not user:
        await message.answer(f"❌ لم يتم العثور على المستخدم '{query}' في قاعدة البيانات.")
        return
        
    uid, uname, fname, lname, _, _, _ = user
    unban_user(uid)
    
    name = f"{fname or ''} {lname or ''}".strip() or "بدون اسم"
    await message.answer(
        f"✅ <b>تم إلغاء حظر المستخدم بنجاح!</b>\n\n"
        f"👤 الاسم: <b>{name}</b>\n"
        f"🆔 المعرف: <code>{uid}</code>\n"
        f"🏷 اليوزر: @{uname or 'لا يوجد'}",
        reply_markup=get_admin_keyboard(),
        parse_mode="HTML"
    )
    await state.clear()


# ── Search User ──────────────────────────────────────────────────

@router.message(F.text == "🔍 استعلام عن مستخدم")
async def on_search_user_prompt(message: Message, state: FSMContext) -> None:
    if not is_admin(message):
        return
        
    await state.set_state(AdminStates.waiting_for_search_user)
    await message.answer(
        "🔍 <b>أدخل معرف المستخدم (User ID) أو يوزره (@username) للبحث عنه:</b>",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )


@router.message(AdminStates.waiting_for_search_user, F.text)
async def on_search_user_execute(message: Message, state: FSMContext) -> None:
    if not is_admin(message):
        return
        
    query = message.text.strip()
    from ..services.user_service import search_user
    
    user = search_user(query)
    if not user:
        await message.answer(f"❌ لم يتم العثور على المستخدم '{query}' في قاعدة البيانات.")
        return
        
    uid, uname, fname, lname, sub, banned, last_seen = user
    name = f"{fname or ''} {lname or ''}".strip() or "بدون اسم"
    sub_status = "✅ مشترك" if sub else "❌ غير مشترك"
    ban_status = "🚫 محظور" if banned else "🟢 نشط"
    
    text = (
        f"🔍 <b>تفاصيل حساب المستخدم:</b>\n\n"
        f"👤 الاسم: <b>{name}</b>\n"
        f"🆔 معرف: <code>{uid}</code>\n"
        f"🏷 يوزر: @{uname or 'لا يوجد'}\n"
        f"📢 الاشتراك: <b>{sub_status}</b>\n"
        f"🛡 الحالة: <b>{ban_status}</b>\n"
        f"⏱ آخر تواجد: <code>{last_seen}</code>"
    )
    
    await message.answer(text, reply_markup=get_admin_keyboard(), parse_mode="HTML")
    await state.clear()


# ── Shutdown Local Instance ──────────────────────────────────────

@router.message(F.text == "/shutdown_local")
async def on_shutdown_local(message: Message) -> None:
    if not is_admin(message):
        return
        
    # Render sets RENDER=true automatically
    is_render = os.environ.get("RENDER") == "true"
    
    if not is_render:
        await message.answer("🛑 <b>جاري إيقاف البوت المحلي (القديم)...</b>\nسيتم إغلاق هذه النسخة الآن.", parse_mode="HTML")
        await asyncio.sleep(1)
        logger.info("Shutdown requested via /shutdown_local command.")
        sys.exit(0)
    else:
        await message.answer("ℹ️ <b>هذا البوت يعمل على Render (النسخة النشطة).</b>\nلم يتم إيقافه لأن البيئة سحابية.", parse_mode="HTML")