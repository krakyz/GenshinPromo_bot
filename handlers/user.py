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
    get_code_activation_keyboard,
    get_code_confirmation_keyboard
)
from utils.date_utils import get_moscow_time, format_expiry_date

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
        
        base_text = f"""🎮 <b>Добро пожаловать в Genshin Promo Bot</b>

🤖 <b>Что умеет этот бот:</b>
– Показывать актуальные промо-коды
– Уведомлять о новых кодах
– Предоставлять удобные ссылки для активации

💾 <b>Доступные команды:</b>
/codes — все активные коды
/subscribe — подписаться на уведомления
/unsubscribe — отписаться от уведомлений
/help — справка"""
        
        if not is_subscribed:
            base_text += "\n\n🔔 <b>Совет:</b> Подпишись на уведомления, чтобы первым узнавать о новых кодах!"
        
        return base_text
    
    @staticmethod
    def codes_list_message(codes) -> str:
        """Сообщение со списком кодов"""
        if not codes:
            return """🤷‍♂️ <b>Активных промо-кодов пока нет</b>

Такое вообще бывает? GENSHINGIFT разве не вечный? Скорее всего с ботом что-то не так."""
        
        text = f"<b>Активные промо-коды ({len(codes)}):</b>\n\n"
        
        for code in codes:
            text += f"<code>{code.code}</code>\n"
            text += f"<i>{code.description or 'MISSING_CODE'}</i>\n"
            text += f"<i>{code.rewards or 'Не указано'}</i>\n"
            if code.expires_date:
                text += f"⏰ Активен до {format_expiry_date(code.expires_date)}\n\n"
            else:
                text += f"\n"
            
        return text
    
    @staticmethod
    def help_message() -> str:
        """Справка"""
        return """🤖 <b>Что умеет этот бот:</b>
— Показывать актуальные промо-коды
— Уведомлять о новых кодах
— Предоставлять удобные ссылки для активации

💾 <b>Доступные команды:</b>
— /codes - все активные коды
— /subscribe - подписаться на уведомления
— /unsubscribe - отписаться от уведомлений
— /help - справка

❓ <b>Как активировать код:</b>
1. Нажми на кнопку с кодом
2. Войди в аккаунт HoYoverse
3. Выбери профиль и регион сервера
4. Подтверди активацию

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

@router.callback_query(lambda c: c.data and c.data.startswith("check_code_"))
async def check_code_validity(callback: CallbackQuery):
    """
    🎯 КЛЮЧЕВАЯ ФУНКЦИЯ: Проверка актуальности кода перед переходом на сайт
    Вызывается при клике на код в списке всех кодов
    """
    try:
        # Извлекаем код из callback_data
        code_value = callback.data.replace("check_code_", "")
        logger.info(f"🔍 Проверяю актуальность кода: {code_value}")
        
        # Проверяем актуальность кода в БД
        active_codes = await db.get_active_codes()
        code_exists = False
        code_obj = None
        
        for code in active_codes:
            if code.code == code_value:
                code_exists = True
                code_obj = code
                break
        
        if not code_exists:
            # Код не найден или неактивен
            logger.info(f"❌ Код {code_value} не найден или неактивен")
            
            await callback.answer(
                f"❌ Промо-код {code_value} больше недействителен или истек!",
                show_alert=True
            )
            return
        
        # Дополнительная проверка на истечение по времени (если есть expires_date)
        if code_obj and code_obj.expires_date:
            moscow_now = get_moscow_time()
            if moscow_now >= code_obj.expires_date:
                logger.info(f"⏰ Код {code_value} истек по времени")
                
                await callback.answer(
                    f"⏰ Промо-код {code_value} истек {code_obj.expires_date.strftime('%d.%m.%Y %H:%M')}!",
                    show_alert=True
                )
                return
        
        # Код актуален! Показываем подтверждение перехода
        logger.info(f"✅ Код {code_value} актуален, показываю подтверждение")
        
        confirmation_text = f"""✅ <b>Промо-код актуален!</b>

🎁 <b>Код:</b> <code>{code_value}</code>
💎 <b>Награды:</b> {code_obj.rewards or 'Не указано'}
📝 <b>Описание:</b> {code_obj.description or 'Промо-код Genshin Impact'}"""

        if code_obj.expires_date:
            from utils.date_utils import format_expiry_date
            confirmation_text += f"\n⏰ <b>Действует до:</b> {format_expiry_date(code_obj.expires_date)}"
        
        confirmation_text += "\n\n🌐 <i>Нажми кнопку ниже, чтобы перейти на сайт активации HoYoverse</i>"
        
        await callback.message.edit_text(
            confirmation_text,
            parse_mode="HTML",
            reply_markup=get_code_confirmation_keyboard(code_value)
        )
        
        await callback.answer("✅ Код проверен!")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при проверке кода: {e}")
        await callback.answer(
            "❌ Произошла ошибка при проверке кода. Попробуй еще раз.",
            show_alert=True
        )


# Обработчик кнопки "Назад к кодам" из подтверждения
@router.callback_query(F.data == "back_to_codes")  
async def back_to_codes_callback(callback: CallbackQuery):
    """Возврат к списку кодов из подтверждения"""
    try:
        # Получаем актуальные коды
        codes = await db.get_active_codes()
        
        if not codes:
            codes_text = """🤷‍♂️ <b>Активных промо-кодов нет</b>

Подпишись на уведомления, чтобы не пропустить новые коды!"""
            
            from keyboards.inline import get_subscription_keyboard
            is_subscribed = len(await db.get_all_subscribers()) > 0  # Упрощенная проверка
            keyboard = get_subscription_keyboard(is_subscribed)
        else:
            codes_text = f"""📋 <b>Все активные промо-коды ({len(codes)}):</b>

💡 <i>Нажми на код, чтобы проверить его актуальность перед активацией</i>"""
            
            from keyboards.inline import get_all_codes_keyboard
            keyboard = get_all_codes_keyboard(codes)
        
        await callback.message.edit_text(
            codes_text,
            parse_mode="HTML", 
            reply_markup=keyboard
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"❌ Ошибка при возврате к кодам: {e}")
        await callback.answer("❌ Ошибка загрузки кодов", show_alert=True)


# Дополнительная функция для получения информации о коде по значению
async def get_code_by_value(code_value: str):
    """Вспомогательная функция для получения кода по значению"""
    try:
        active_codes = await db.get_active_codes()
        for code in active_codes:
            if code.code == code_value:
                return code
        return None
    except Exception as e:
        logger.error(f"Ошибка получения кода {code_value}: {e}")
        return None


# Функция для проверки множественных кодов (если понадобится в будущем)
async def check_multiple_codes_validity():
    """Массовая проверка актуальности всех кодов"""
    try:
        codes = await db.get_active_codes()
        moscow_now = get_moscow_time()
        
        valid_codes = []
        expired_codes = []
        
        for code in codes:
            if code.expires_date and moscow_now >= code.expires_date:
                expired_codes.append(code)
            else:
                valid_codes.append(code)
        
        logger.info(f"📊 Проверка кодов: {len(valid_codes)} актуальных, {len(expired_codes)} истекших")
        
        return {
            'valid': valid_codes,
            'expired': expired_codes,
            'total': len(codes)
        }
        
    except Exception as e:
        logger.error(f"Ошибка массовой проверки кодов: {e}")
        return {'valid': [], 'expired': [], 'total': 0}