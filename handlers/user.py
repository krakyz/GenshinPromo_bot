from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database import db
from models import UserModel
from keyboards.inline import get_subscription_keyboard, get_code_activation_keyboard, get_all_codes_keyboard
import logging

logger = logging.getLogger(__name__)
router = Router()

@router.message(CommandStart())
async def start_handler(message: Message):
    """Обработчик команды /start"""
    user = UserModel(
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name
    )
    
    await db.add_user(user)
    
    welcome_text = f"""
🎮 <b>Добро пожаловать в бот промо-кодов Genshin Impact!</b>

Привет, {message.from_user.first_name}! 👋

Этот бот поможет тебе не пропустить ни одного промо-кода для Genshin Impact!

🔔 <b>Что я умею:</b>
• Отправляю уведомления о новых промо-кодах
• Показываю активные коды с кнопками для активации
• Помогаю управлять подпиской на уведомления

📱 <b>Доступные команды:</b>
/codes - показать все активные коды
/subscribe - подписаться на уведомления
/unsubscribe - отписаться от уведомлений
/help - показать справку

Удачи в путешествии по Тейвату! ✨
"""
    
    await message.answer(
        welcome_text,
        parse_mode="HTML",
        reply_markup=get_subscription_keyboard()
    )

@router.message(Command("codes"))
@router.callback_query(lambda c: c.data == "view_all_codes")
async def codes_handler(update):
    """Обработчик команды /codes - показать все активные коды одним сообщением"""
    
    # Добавим отладку
    await db.debug_codes()
    
    codes = await db.get_active_codes()
    logger.info(f"Получено кодов: {len(codes)}")
    
    # Определяем тип обновления (сообщение или callback)
    if isinstance(update, Message):
        message = update
        edit_message = False
    else:  # CallbackQuery
        message = update.message
        edit_message = True
        await update.answer()
    
    if not codes:
        text = (
            "🤷‍♂️ <b>Активных промо-кодов пока нет</b>\n\n"
            "Подпишись на уведомления, чтобы узнать о новых кодах первым!"
        )
        keyboard = get_subscription_keyboard()
        
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
            logger.info(f"Код {code.code} имеет expires_date: {code.expires_date}")
            codes_text += f"⏰ Действует до: {code.expires_date.strftime('%d.%m.%Y %H:%M')}\n"
        else:
            logger.info(f"Код {code.code} НЕ имеет expires_date")
        
        codes_text += "\n"
    
    codes_text += "💡 <i>Нажми на кнопку с кодом ниже для активации!</i>"
    
    # Создаем клавиатуру со всеми кодами
    keyboard = get_all_codes_keyboard(codes)
    
    if edit_message:
        await message.edit_text(codes_text, parse_mode="HTML", reply_markup=keyboard)
    else:
        await message.answer(codes_text, parse_mode="HTML", reply_markup=keyboard)

@router.message(Command("help"))
async def help_handler(message: Message):
    """Обработчик команды /help"""
    help_text = """
📚 <b>Справка по боту Genshin Impact промо-кодов</b>

🤖 <b>Основные команды:</b>
/start - запустить бота и подписаться
/codes - показать все активные промо-коды
/subscribe - подписаться на уведомления о новых кодах
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

📢 <b>Уведомления:</b>
Подпишись, чтобы получать мгновенные уведомления о новых промо-кодах!

🎮 Удачи в Genshin Impact!
"""
    
    await message.answer(
        help_text,
        parse_mode="HTML",
        reply_markup=get_subscription_keyboard()
    )

@router.callback_query(lambda c: c.data == "subscribe")
async def subscribe_callback(callback: CallbackQuery):
    """Обработчик подписки на уведомления"""
    success = await db.subscribe_user(callback.from_user.id)
    
    if success:
        await callback.message.edit_text(
            "🔔 <b>Отлично!</b>\n\n"
            "Ты подписался на уведомления о новых промо-кодах Genshin Impact!\n"
            "Теперь ты будешь получать уведомления о каждом новом коде.",
            parse_mode="HTML",
            reply_markup=get_subscription_keyboard()
        )
    else:
        await callback.message.edit_text(
            "❌ <b>Ошибка</b>\n\n"
            "Не удалось подписаться на уведомления. Попробуй позже.",
            parse_mode="HTML",
            reply_markup=get_subscription_keyboard()
        )
    
    await callback.answer()

@router.callback_query(lambda c: c.data == "unsubscribe")
async def unsubscribe_callback(callback: CallbackQuery):
    """Обработчик отписки от уведомлений"""
    success = await db.unsubscribe_user(callback.from_user.id)
    
    if success:
        await callback.message.edit_text(
            "🔕 <b>Готово!</b>\n\n"
            "Ты отписался от уведомлений о промо-кодах.\n"
            "Ты все еще можешь просматривать активные коды командой /codes",
            parse_mode="HTML",
            reply_markup=get_subscription_keyboard()
        )
    else:
        await callback.message.edit_text(
            "❌ <b>Ошибка</b>\n\n"
            "Не удалось отписаться от уведомлений. Попробуй позже.",
            parse_mode="HTML",
            reply_markup=get_subscription_keyboard()
        )
    
    await callback.answer()

@router.message(Command("subscribe"))
async def subscribe_command(message: Message):
    """Команда подписки"""
    success = await db.subscribe_user(message.from_user.id)
    
    if success:
        await message.answer(
            "🔔 <b>Отлично!</b>\n\n"
            "Ты подписался на уведомления о новых промо-кодах Genshin Impact!",
            parse_mode="HTML"
        )
    else:
        await message.answer(
            "❌ Не удалось подписаться на уведомления. Попробуй позже.",
            parse_mode="HTML"
        )

@router.message(Command("unsubscribe"))
async def unsubscribe_command(message: Message):
    """Команда отписки"""
    success = await db.unsubscribe_user(message.from_user.id)
    
    if success:
        await message.answer(
            "🔕 <b>Готово!</b>\n\n"
            "Ты отписался от уведомлений о промо-кодах.",
            parse_mode="HTML"
        )
    else:
        await message.answer(
            "❌ Не удалось отписаться от уведомлений. Попробуй позже.",
            parse_mode="HTML"
        )