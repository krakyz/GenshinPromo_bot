from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database import db
from models import UserModel
from keyboards.inline import get_subscription_keyboard, get_all_codes_keyboard
from utils.date_utils import format_expiry_date
import logging

logger = logging.getLogger(__name__)
router = Router()

async def get_user_subscription_status(user_id: int) -> bool:
    """Получить статус подписки пользователя"""
    try:
        # Проверяем статус подписки в базе данных
        subscribers = await db.get_all_subscribers()
        return user_id in subscribers
    except Exception as e:
        logger.error(f"Ошибка при проверке статуса подписки: {e}")
        return False

@router.message(CommandStart())
async def start_handler(message: Message):
    """Обработчик команды /start"""
    user = UserModel(
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name
    )
    
    await db.add_user(user)
    
    # Проверяем статус подписки
    is_subscribed = await get_user_subscription_status(message.from_user.id)
    
    welcome_text = f"""
🎮 <b>Добро пожаловать в бот промо-кодов Genshin Impact!</b>

Привет, {message.from_user.first_name}! 👋

Этот бот поможет тебе не пропустить ни одного промо-кода для Genshin Impact!

🔔 <b>Что я умею:</b>
• Отправляю уведомления о новых промо-кодах
• Показываю активные коды с кнопками для активации
• Помогаю найти самые свежие промо-коды

📱 <b>Доступные команды:</b>
/codes - показать все активные коды
/subscribe - подписаться на уведомления
/unsubscribe - отписаться от уведомлений
/help - показать справку

⏰ <i>Все сроки указаны в московском времени (МСК)</i>

Удачи в путешествии по Тейвату! ✨
"""
    
    if is_subscribed:
        welcome_text += "\n✅ <i>Ты уже подписан на уведомления о новых кодах!</i>"
    
    await message.answer(
        welcome_text,
        parse_mode="HTML",
        reply_markup=get_subscription_keyboard(is_subscribed)
    )

@router.message(Command("codes"))
@router.callback_query(lambda c: c.data == "view_all_codes")
async def codes_handler(update):
    """Обработчик команды /codes - показать все активные коды одним сообщением"""
    codes = await db.get_active_codes()
    logger.info(f"Получено кодов: {len(codes)}")
    
    # Определяем тип обновления (сообщение или callback)
    if isinstance(update, Message):
        message = update
        edit_message = False
        user_id = message.from_user.id
    else:  # CallbackQuery
        message = update.message
        edit_message = True
        user_id = update.from_user.id
        await update.answer()
    
    if not codes:
        # Проверяем статус подписки для показа правильной клавиатуры
        is_subscribed = await get_user_subscription_status(user_id)
        
        text = (
            "🤷‍♂️ <b>Активных промо-кодов пока нет</b>\n\n"
        )
        
        if not is_subscribed:
            text += "Подпишись на уведомления, чтобы узнать о новых кодах первым!"
        else:
            text += "Как только появятся новые коды, ты получишь уведомление!"
        
        keyboard = get_subscription_keyboard(is_subscribed)
        
        if edit_message:
            await message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        else:
            await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
        return
    
    # Формируем текст со всеми кодами
    codes_text = f"🎁 <b>Активные промо-коды ({len(codes)}):</b>\n\n"
    
    for i, code in enumerate(codes, 1):
        codes_text += f"<b>{i}. {code.code}</b>\n"
        
        # Добавляем награды если указаны
        if code.rewards:
            codes_text += f"💎 {code.rewards}\n"
        
        # Добавляем описание если указано
        if code.description and code.description != code.code:
            codes_text += f"📝 {code.description}\n"
        
        # Добавляем информацию о сроке истечения если она есть
        if code.expires_date:
            expires_text = format_expiry_date(code.expires_date)
            codes_text += f"⏰ Действует до: {expires_text}\n"
        
        codes_text += "\n"
    
    codes_text += "💡 <i>Нажми на кнопку с кодом ниже для активации!</i>\n"
    codes_text += "⏰ <i>Время указано в МСК (московское время)</i>"
    
    # Создаем клавиатуру со всеми кодами
    keyboard = get_all_codes_keyboard(codes)
    
    if edit_message:
        await message.edit_text(codes_text, parse_mode="HTML", reply_markup=keyboard)
    else:
        await message.answer(codes_text, parse_mode="HTML", reply_markup=keyboard)

@router.message(Command("help"))
async def help_handler(message: Message):
    """Обработчик команды /help"""
    # Проверяем статус подписки
    is_subscribed = await get_user_subscription_status(message.from_user.id)
    
    help_text = """
📚 <b>Справка по боту Genshin Impact промо-кодов</b>

🤖 <b>Основные команды:</b>
/start - запустить бота
/codes - показать все активные промо-коды
/subscribe - подписаться на уведомления
/unsubscribe - отписаться от уведомлений
/help - показать эту справку

🎁 <b>Как активировать промо-код:</b>
1. Получи код через этого бота
2. Нажми кнопку с названием кода
3. Войди в свой аккаунт HoYoverse
4. Выбери сервер и введи никнейм персонажа
5. Получи награды в игре через почту

⚠️ <b>Важно знать:</b>
• Каждый код можно использовать только один раз
• Коды имеют ограниченное время действия
• Для активации нужен Adventure Rank 10+
• ⏰ Все сроки указаны в московском времени (МСК)
"""
    
    if not is_subscribed:
        help_text += "\n📢 <b>Уведомления:</b>\nПодпишись, чтобы получать мгновенные уведомления о новых промо-кодах!"
    else:
        help_text += "\n✅ <b>Ты подписан на уведомления!</b>\nТы будешь получать все новые промо-коды автоматически."
    
    help_text += "\n\n🎮 Удачи в Genshin Impact!"
    
    await message.answer(
        help_text,
        parse_mode="HTML",
        reply_markup=get_subscription_keyboard(is_subscribed)
    )

@router.callback_query(lambda c: c.data == "subscribe")
async def subscribe_callback(callback: CallbackQuery):
    """Обработчик подписки на уведомления"""
    success = await db.subscribe_user(callback.from_user.id)
    
    if success:
        await callback.message.edit_text(
            "🔔 <b>Отлично!</b>\n\n"
            "Ты подписался на уведомления о новых промо-кодах Genshin Impact!\n"
            "Теперь ты будешь получать уведомления о каждом новом коде.\n\n"
            "⏰ <i>Все сроки указаны в московском времени (МСК)</i>\n\n"
            "✨ <i>Используй кнопку ниже, чтобы посмотреть все доступные коды!</i>\n\n"
            "💡 <i>Для отписки используй команду /unsubscribe</i>",
            parse_mode="HTML",
            reply_markup=get_subscription_keyboard(is_subscribed=True)  # Теперь подписан
        )
    else:
        await callback.message.edit_text(
            "❌ <b>Ошибка</b>\n\n"
            "Не удалось подписаться на уведомления. Попробуй позже.",
            parse_mode="HTML",
            reply_markup=get_subscription_keyboard(is_subscribed=False)
        )
    
    await callback.answer("Подписка оформлена! 🎉")

@router.message(Command("subscribe"))
async def subscribe_command(message: Message):
    """Команда подписки"""
    # Проверяем, не подписан ли уже
    is_subscribed = await get_user_subscription_status(message.from_user.id)
    
    if is_subscribed:
        await message.answer(
            "✅ <b>Ты уже подписан!</b>\n\n"
            "Ты получаешь уведомления о всех новых промо-кодах Genshin Impact.\n\n"
            "💡 <i>Для отписки используй команду /unsubscribe</i>",
            parse_mode="HTML",
            reply_markup=get_subscription_keyboard(is_subscribed=True)
        )
        return
    
    success = await db.subscribe_user(message.from_user.id)
    
    if success:
        await message.answer(
            "🔔 <b>Отлично!</b>\n\n"
            "Ты подписался на уведомления о новых промо-кодах Genshin Impact!\n\n"
            "💡 <i>Для отписки используй команду /unsubscribe</i>",
            parse_mode="HTML",
            reply_markup=get_subscription_keyboard(is_subscribed=True)
        )
    else:
        await message.answer(
            "❌ Не удалось подписаться на уведомления. Попробуй позже.",
            parse_mode="HTML",
            reply_markup=get_subscription_keyboard(is_subscribed=False)
        )

@router.message(Command("unsubscribe"))
async def unsubscribe_command(message: Message):
    """Команда отписки"""
    # Проверяем, подписан ли пользователь
    is_subscribed = await get_user_subscription_status(message.from_user.id)
    
    if not is_subscribed:
        await message.answer(
            "ℹ️ <b>Ты не подписан на уведомления</b>\n\n"
            "Для подписки используй команду /subscribe или нажми кнопку ниже.",
            parse_mode="HTML",
            reply_markup=get_subscription_keyboard(is_subscribed=False)
        )
        return
    
    success = await db.unsubscribe_user(message.from_user.id)
    
    if success:
        await message.answer(
            "🔕 <b>Готово!</b>\n\n"
            "Ты отписался от уведомлений о промо-кодах.\n"
            "Ты все еще можешь просматривать активные коды командой /codes\n\n"
            "💡 <i>Для повторной подписки используй команду /subscribe</i>",
            parse_mode="HTML",
            reply_markup=get_subscription_keyboard(is_subscribed=False)
        )
        logger.info(f"Пользователь {message.from_user.id} отписался через команду")
    else:
        await message.answer(
            "❌ Не удалось отписаться от уведомлений. Попробуй позже.",
            parse_mode="HTML",
            reply_markup=get_subscription_keyboard(is_subscribed=True)
        )

# Callback для истекших кодов
@router.callback_query(lambda c: c.data == "expired_code")
async def expired_code_callback(callback: CallbackQuery):
    """Обработчик нажатий на истекшие коды"""
    await callback.answer(
        "⌛ Этот промо-код больше не действует. Следи за новыми кодами!",
        show_alert=True
    )