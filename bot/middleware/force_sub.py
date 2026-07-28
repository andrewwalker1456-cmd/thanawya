from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware, Bot
from aiogram.types import TelegramObject, Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramAPIError
import logging

logger = logging.getLogger(__name__)

class ForceSubMiddleware(BaseMiddleware):
    def __init__(self, channel_username: str, channel_url: str):
        self.channel_username = channel_username
        self.channel_url = channel_url

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        
        bot: Bot = data.get("bot")
        
        # Get user from message or callback
        user = None
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user
            
        if not user or not bot:
            return await handler(event, data)
            
        # Ignore inline queries or other updates for now
        if user.is_bot:
             return await handler(event, data)

        # Register/update user
        from ..services.user_service import register_user, set_subscription_status, is_user_banned
        register_user(user_id=user.id, username=user.username, first_name=user.first_name, last_name=user.last_name)

        # Check if user is banned
        if is_user_banned(user.id):
            ban_text = "🚫 <b>تم حظر حسابك من استخدام هذا البوت.</b>\n\nيرجى التواصل مع الإدارة إذا كنت تعتقد أن هذا خطأ."
            if isinstance(event, Message):
                await event.answer(ban_text, parse_mode="HTML")
            elif isinstance(event, CallbackQuery):
                await event.answer(ban_text.replace("<b>", "").replace("</b>", ""), show_alert=True)
            return  # Drop the update and block access

        try:
            member = await bot.get_chat_member(chat_id=self.channel_username, user_id=user.id)
            if member.status in ['left', 'kicked', 'restricted']:
                set_subscription_status(user.id, False)
                await self._prompt_join(event, bot)
                return  # Drop the update
            
            # User is subscribed
            set_subscription_status(user.id, True)
            
            # If it's a callback query specifically for checking sub, answer it
            if isinstance(event, CallbackQuery) and event.data == "check_sub":
                await event.answer("✅ شكراً لك! يمكنك الآن استخدام البوت.", show_alert=True)
                # Delete the forced sub message
                try:
                    await event.message.delete()
                except Exception:
                    pass
                
                # Send the main menu
                try:
                    from ..handlers.shared import get_main_keyboard
                    await bot.send_message(
                        chat_id=user.id,
                        text="🎓 <b>نتيجة الثانوية العامة 2026</b>\n\nاختر من القائمة أدناه للبحث عن النتيجة:",
                        reply_markup=get_main_keyboard(),
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Failed to send main menu after sub check: {e}")
                    
                return  # Stop propagation since it's just a check button
                
        except TelegramAPIError as e:
            # Bot might not be admin in the channel or channel doesn't exist
            logger.error(f"Force sub error (is bot admin in channel?): {e}")
            # Failsafe: if we can't check, let them through so the bot doesn't break completely
            return await handler(event, data)
            
        return await handler(event, data)
        
    async def _prompt_join(self, event: TelegramObject, bot: Bot):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 اشترك في القناة", url=self.channel_url)],
            [InlineKeyboardButton(text="🔄 تحقق من الاشتراك", callback_data="check_sub")]
        ])
        
        text = (
            "⚠️ <b>عذراً، يجب عليك الاشتراك في قناة البوت أولاً!</b>\n\n"
            "اشترك في القناة ثم اضغط على زر التحقق لتتمكن من استخدام البوت مجاناً."
        )
        
        if isinstance(event, Message):
            await event.answer(text, reply_markup=keyboard, parse_mode="HTML")
        elif isinstance(event, CallbackQuery):
            await event.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
            await event.answer("يجب الاشتراك في القناة أولاً!", show_alert=True)
