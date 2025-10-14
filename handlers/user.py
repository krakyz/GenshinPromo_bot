"""
Оптимизированный модуль пользовательских обработчиков
"""
import logging
from typing import Dict, Any

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database import db
from models import UserModel
from keyboards.inline import (
    get_subscription_keyboard,
    get_all_codes_keyboard,
    get_code_activation_keyboard
)
from utils.date_utils import format_expiry_date

logger = logging.getLogger(__name__)
router = Router()


class UserService:
    """Сервис для работы с пользователями"""
    
    @staticmethod
    async def get_user_subscription_status(user_id: int) -> bool:
        """Проверяет статус подписки пользователя"""
        try:
            subscribers = await db.get_all_subscribers()
            return user_id in subscribers
        except Exception as e:
            logger.error(f"Ошибка проверки подписки: {e}")
            return False
    
    @staticmethod
    async def register_user(user_id: int, username: str = None, first_name: str = None) -> bool:
        """Регистрирует нового пользователя"""
        try:
            user = UserModel(
                user_id=user_id,
                username=username,
                first_name=first_name
            )
            return await db.add_user(user)
        except Exception as e:
            logger.error(f"Ошибка регистрации пользователя {user_id}: {e}")
            return False


class MessageTemplates:
    """Шаблоны сообщений для пользователей"""
    
    @staticmethod
    def welcome_message(first_name: str, is_subscribed: bool) -> str:
        """Приветственное сообщение"""
        greeting = f"Привет, {first_name}!" if first_name else "Привет!"
        
        base_text = f"""🎮 <b>Добро пожаловать в бота Genshin Impact кодов!</b>

{greeting}

🎁 <b>Что я умею:</b>
• Показывать актуальные промо-коды
• Уведомлять о новых кодах (подписка)
• Предоставлять прямые ссылки для активации

📋 <b>Доступные команды:</b>
• /codes - все активные коды
• /subscribe - подписаться на уведомления
• /unsubscribe - отписаться от уведомлений
• /help - помощь

<i>💡 Нажми на кнопки ниже для быстрого доступа!</i>"""
        
        if not is_subscribed:
            base_text += "\n\n🔔 <b>Совет:</b> Подпишись на уведомления, чтобы первым узнавать о новых кодах!"
        
        return base_text
    
    @staticmethod
    def codes_list_message(codes) -> str:
        """Сообщение со списком кодов"""
        if not codes:
            return """🤷‍♂️ <b>Активных промо-кодов пока нет</b>

Такое вообще бывает? GENSHINGIFT разве не вечный? Скорее всего с ботом что-то не так.

🔔 Не забудь подписаться на обновления."""
        
        text = f"🎁 <b>Активные промо-коды ({len(codes)}):</b>\n\n"
        
        for code in codes:
            text += f"🔥 <code>{code.code}</code>\n"
            text += f"<i>{code.description or 'MISSING_CODE'}</i>\n"
            text += f"💎 {code.rewards or 'Не указано'}\n\n"
            
            if code.expires_date:
                text += f"⏰ До: {format_expiry_date(code.expires_date)}\n"
            
            text += "────────────┈┈┈┄┄╌╌╌╌┄┄┈┈┈────────────\n\n"
        
        text += "<i>💡 Нажми на название кода для быстрой активации!</i>"
        return text
    
    @staticmethod
    def help_message() -> str:
        """Справочное сообщение"""
        return """📚 <b>Справка по боту</b>

🎯 <b>Основные функции:</b>
• Просмотр актуальных промо-кодов
• Уведомления о новых кодах
• Быстрая активация в один клик

⌨️ <b>Команды:</b>
• /start - главное меню
• /codes - показать все коды
• /subscribe - подписаться на уведомления
• /unsubscribe - отписаться от уведомлений
• /help - эта справка

🔔 <b>Подписка:</b>
Подписавшись на уведомления, ты будешь получать сообщения о каждом новом промо-коде сразу после его публикации.

❓ <b>Как активировать код:</b>
1. Нажми на кнопку с кодом
2. Войди в аккаунт HoYoverse
3. Подтверди активацию

<i>💡 Коды можно активировать и в самой игре через меню настроек!</i>"""


@router.message(CommandStart())
async def start_handler(message: Message):
    """Обработчик команды /start"""
    # Регистрируем пользователя
    await UserService.register_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name
    )
    
    # Проверяем статус подписки
    is_subscribed = await UserService.get_user_subscription_status(message.from_user.id)
    
    # Отправляем приветствие
    welcome_text = MessageTemplates.welcome_message(message.from_user.first_name, is_subscribed)
    
    await message.answer(
        welcome_text,
        parse_mode="HTML",
        reply_markup=get_subscription_keyboard(is_subscribed)
    )


@router.message(Command("codes"))
async def codes_handler(message: Message):
    """Обработчик команды /codes"""
    try:
        codes = await db.get_active_codes()
        codes_text = MessageTemplates.codes_list_message(codes)
        
        if codes:
            keyboard = get_all_codes_keyboard(codes)
        else:
            is_subscribed = await UserService.get_user_subscription_status(message.from_user.id)
            keyboard = get_subscription_keyboard(is_subscribed)
        
        await message.answer(codes_text, parse_mode="HTML", reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Ошибка получения кодов: {e}")
        await message.answer(
            "❌ <b>Произошла ошибка при получении кодов</b>\n\nПопробуй еще раз позже.",
            parse_mode="HTML"
        )


@router.message(Command("subscribe"))
async def subscribe_handler(message: Message):
    """Обработчик команды /subscribe"""
    try:
        is_subscribed = await UserService.get_user_subscription_status(message.from_user.id)
        
        if is_subscribed:
            await message.answer(
                "🔔 <b>Ты уже подписан на уведомления!</b>\n\n"
                "Ты будешь получать сообщения о каждом новом промо-коде.\n\n"
                "💡 Для отписки используй команду /unsubscribe",
                parse_mode="HTML",
                reply_markup=get_subscription_keyboard(True)
            )
        else:
            success = await db.subscribe_user(message.from_user.id)
            
            if success:
                await message.answer(
                    "✅ <b>Подписка активирована!</b>\n\n"
                    "🎉 Теперь ты будешь получать уведомления о новых промо-кодах первым!\n\n"
                    "💡 Для отписки используй команду /unsubscribe",
                    parse_mode="HTML",
                    reply_markup=get_subscription_keyboard(True)
                )
            else:
                await message.answer(
                    "❌ <b>Ошибка подписки</b>\n\nПопробуй еще раз позже.",
                    parse_mode="HTML"
                )
    
    except Exception as e:
        logger.error(f"Ошибка подписки пользователя {message.from_user.id}: {e}")
        await message.answer(
            "❌ <b>Произошла ошибка</b>\n\nПопробуй еще раз позже.",
            parse_mode="HTML"
        )


@router.message(Command("unsubscribe"))
async def unsubscribe_handler(message: Message):
    """Обработчик команды /unsubscribe"""
    try:
        is_subscribed = await UserService.get_user_subscription_status(message.from_user.id)
        
        if not is_subscribed:
            await message.answer(
                "ℹ️ <b>Ты не подписан на уведомления</b>\n\n"
                "Для подписки используй команду /subscribe или нажми кнопку ниже.",
                parse_mode="HTML",
                reply_markup=get_subscription_keyboard(False)
            )
        else:
            success = await db.unsubscribe_user(message.from_user.id)
            
            if success:
                await message.answer(
                    "🔕 <b>Готово!</b>\n\n"
                    "Ты отписался от уведомлений о промо-кодах.\n"
                    "Ты все еще можешь просматривать активные коды командой /codes\n\n"
                    "💡 Для повторной подписки используй команду /subscribe",
                    parse_mode="HTML",
                    reply_markup=get_subscription_keyboard(False)
                )
            else:
                await message.answer(
                    "❌ <b>Ошибка отписки</b>\n\nПопробуй еще раз позже.",
                    parse_mode="HTML"
                )
    
    except Exception as e:
        logger.error(f"Ошибка отписки пользователя {message.from_user.id}: {e}")
        await message.answer(
            "❌ <b>Произошла ошибка</b>\n\nПопробуй еще раз позже.",
            parse_mode="HTML"
        )


@router.message(Command("help"))
async def help_handler(message: Message):
    """Обработчик команды /help"""
    help_text = MessageTemplates.help_message()
    
    is_subscribed = await UserService.get_user_subscription_status(message.from_user.id)
    
    await message.answer(
        help_text,
        parse_mode="HTML",
        reply_markup=get_subscription_keyboard(is_subscribed)
    )


# Обработчики callback запросов
@router.callback_query(F.data == "subscribe")
async def subscribe_callback(callback: CallbackQuery):
    """Обработчик кнопки подписки"""
    success = await db.subscribe_user(callback.from_user.id)
    
    if success:
        await callback.answer("✅ Подписка активирована!", show_alert=True)
        await callback.message.edit_reply_markup(
            reply_markup=get_subscription_keyboard(True)
        )
    else:
        await callback.answer("❌ Ошибка подписки", show_alert=True)


@router.callback_query(F.data == "view_all_codes")
async def view_all_codes_callback(callback: CallbackQuery):
    """Обработчик кнопки просмотра всех кодов"""
    try:
        codes = await db.get_active_codes()
        codes_text = MessageTemplates.codes_list_message(codes)
        
        if codes:
            keyboard = get_all_codes_keyboard(codes)
        else:
            is_subscribed = await UserService.get_user_subscription_status(callback.from_user.id)
            keyboard = get_subscription_keyboard(is_subscribed)
        
        await callback.message.edit_text(
            codes_text,
            parse_mode="HTML",
            reply_markup=keyboard
        )
        
    except Exception as e:
        logger.error(f"Ошибка просмотра кодов: {e}")
        await callback.answer("❌ Ошибка загрузки кодов", show_alert=True)
    
    await callback.answer()


@router.callback_query(F.data == "expired_code")
async def expired_code_callback(callback: CallbackQuery):
    """Обработчик нажатий на истекшие коды"""
    await callback.answer(
        "⌛ Этот промо-код больше не действует. Следите за новыми кодами!",
        show_alert=True
    )