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
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton, Document,
)
from aiogram.fsm.context import FSMContext

from ..app_state import (
    get_config, get_search_engine, get_importer, get_stats_service,
)
from .shared import AdminStates, get_main_keyboard

logger = logging.getLogger(__name__)

router = Router()


def is_admin(message: Message) -> bool:
    config = get_config()
    user_id = message.from_user.id if message.from_user else 0
    return user_id in config.bot.admin_ids


# ── Admin Entry Point ────────────────────────────────────────────

@router.message(F.text == "/admin")
async def on_admin_entry(message: Message) -> None:
    if not is_admin(message):
        return

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📤 رفع ملف جديد"),
                KeyboardButton(text="📊 الإحصائيات"),
            ],
            [
                KeyboardButton(text="🩺 صحة النظام"),
                KeyboardButton(text="📜 سجل الأخطاء"),
            ],
            [
                KeyboardButton(text="👥 المشتركون"),
                KeyboardButton(text="🔄 إعادة استيراد"),
            ],
            [
                KeyboardButton(text="🔙 القائمة الرئيسية"),
            ],
        ],
        resize_keyboard=True,
    )

    await message.answer(
        "🔧 <b>لوحة تحكم المسؤول</b>\n\nاختر أحد الخيارات:",
        reply_markup=keyboard,
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

@router.message(AdminStates.waiting_for_upload, F.text == "❌ إلغاء")
async def on_admin_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("🏠 القائمة الرئيسية", reply_markup=get_main_keyboard())


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