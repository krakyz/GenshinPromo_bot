from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database import db
from models import UserModel
from keyboards.inline import get_subscription_keyboard, get_code_activation_keyboard

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
async def codes_handler(message: Message):
    """Обработчик команды /codes - показать активные коды"""
    codes = await db.get_active_codes()
    
    if not codes:
        await message.answer(
            "🤷‍♂️ <b>Активных промо-кодов пока нет</b>\n\n"
            "Подпишись на уведомления, чтобы узнать о новых кодах первым!",
            parse_mode="HTML",
            reply_markup=get_subscription_keyboard()
        )
        return
    
    await message.answer(
        f"🎁 <b>Найдено активных кодов: {len(codes)}</b>\n\n"
        "Нажми на кнопку под кодом для активации:",
        parse_mode="HTML"
    )
    
    for code in codes:
        code_text = f"""
🔥 <b>Код:</b> <code>{code.code}</code>

💎 <b>Награды:</b> {code.rewards or 'Не указано'}

📝 <b>Описание:</b> {code.description or 'Промо-код Genshin Impact'}

⏰ <b>Добавлен:</b> {code.created_at.strftime('%d.%m.%Y %H:%M') if code.created_at else 'Не указано'}

<i>💡 Нажми кнопку ниже для активации!</i>
"""
        
        await message.answer(
            code_text,
            parse_mode="HTML",
            reply_markup=get_code_activation_keyboard(code.code)
        )

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
2. Нажми кнопку "Активировать код"
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