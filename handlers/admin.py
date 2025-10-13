from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram import Bot

from database import db
from models import CodeModel
from filters.admin_filter import AdminFilter
from keyboards.inline import get_admin_keyboard, get_code_activation_keyboard
from datetime import datetime
import asyncio
import logging

logger = logging.getLogger(__name__)

router = Router()

class AdminStates(StatesGroup):
    """Состояния для админ-панели"""
    waiting_for_code_data = State()
    waiting_for_code_to_expire = State()

@router.message(Command("admin"), AdminFilter())
async def admin_panel(message: Message):
    """Админ-панель"""
    admin_text = """
🔧 <b>Админ-панель бота Genshin Impact кодов</b>

👋 Привет, администратор!

📊 <b>Доступные действия:</b>
• Добавить новый промо-код
• Деактивировать истекший код
• Просмотреть статистику бота
• Показать все активные коды

Выбери действие из меню ниже:
"""
    
    await message.answer(
        admin_text,
        parse_mode="HTML",
        reply_markup=get_admin_keyboard()
    )

@router.callback_query(lambda c: c.data == "admin_add_code", AdminFilter())
async def add_code_callback(callback: CallbackQuery, state: FSMContext):
    """Начать процесс добавления кода"""
    await callback.message.edit_text(
        "➕ <b>Добавление нового промо-кода</b>\n\n"
        "Отправь данные о промо-коде в следующем формате:\n\n"
        "<code>КОД\n"
        "Описание кода\n"
        "Награды</code>\n\n"
        "<b>Пример:</b>\n"
        "<code>GENSHINGIFT\n"
        "Стандартный промо-код\n"
        "50 Примогемов + 3 Книги героя</code>\n\n"
        "Или отправь /cancel для отмены",
        parse_mode="HTML"
    )
    
    await state.set_state(AdminStates.waiting_for_code_data)
    await callback.answer()

@router.message(AdminStates.waiting_for_code_data, AdminFilter())
async def process_new_code(message: Message, state: FSMContext, bot: Bot):
    """Обработка нового кода от админа"""
    if message.text == "/cancel":
        await message.answer("❌ Добавление кода отменено")
        await state.clear()
        return
    
    try:
        lines = message.text.strip().split('\n')
        if len(lines) < 3:
            await message.answer(
                "❌ <b>Неверный формат!</b>\n\n"
                "Нужно минимум 3 строки:\n"
                "1. Код\n"
                "2. Описание\n"
                "3. Награды",
                parse_mode="HTML"
            )
            return
        
        code = lines[0].strip().upper()
        description = lines[1].strip()
        rewards = lines[2].strip()
        
        # Создаем объект кода
        new_code = CodeModel(
            code=code,
            description=description,
            rewards=rewards
        )
        
        # Добавляем в базу данных
        success = await db.add_code(new_code)
        
        if success:
            await message.answer(
                f"✅ <b>Код успешно добавлен!</b>\n\n"
                f"🔥 <b>Код:</b> <code>{code}</code>\n"
                f"📝 <b>Описание:</b> {description}\n"
                f"💎 <b>Награды:</b> {rewards}",
                parse_mode="HTML"
            )
            
            # Отправляем уведомление всем подписчикам
            await broadcast_new_code(bot, new_code)
            
        else:
            await message.answer(
                f"❌ <b>Ошибка!</b>\n\n"
                f"Код <code>{code}</code> уже существует в базе данных.",
                parse_mode="HTML"
            )
    
    except Exception as e:
        logger.error(f"Ошибка при добавлении кода: {e}")
        await message.answer(
            "❌ <b>Произошла ошибка при добавлении кода</b>\n\n"
            "Проверь формат и попробуй еще раз.",
            parse_mode="HTML"
        )
    
    await state.clear()

@router.callback_query(lambda c: c.data == "admin_expire_code", AdminFilter())
async def expire_code_callback(callback: CallbackQuery, state: FSMContext):
    """Начать процесс деактивации кода"""
    codes = await db.get_active_codes()
    
    if not codes:
        await callback.message.edit_text(
            "🤷‍♂️ <b>Нет активных кодов для деактивации</b>",
            parse_mode="HTML",
            reply_markup=get_admin_keyboard()
        )
        await callback.answer()
        return
    
    codes_list = "\n".join([f"• <code>{code.code}</code>" for code in codes])
    
    await callback.message.edit_text(
        f"❌ <b>Деактивация промо-кода</b>\n\n"
        f"<b>Активные коды:</b>\n{codes_list}\n\n"
        f"Отправь код, который нужно деактивировать, или /cancel для отмены:",
        parse_mode="HTML"
    )
    
    await state.set_state(AdminStates.waiting_for_code_to_expire)
    await callback.answer()

@router.message(AdminStates.waiting_for_code_to_expire, AdminFilter())
async def process_expire_code(message: Message, state: FSMContext, bot: Bot):
    """Обработка деактивации кода"""
    if message.text == "/cancel":
        await message.answer("❌ Деактивация кода отменена")
        await state.clear()
        return
    
    code = message.text.strip().upper()
    success = await db.expire_code(code)
    
    if success:
        await message.answer(
            f"✅ <b>Код деактивирован!</b>\n\n"
            f"Код <code>{code}</code> помечен как истекший.",
            parse_mode="HTML"
        )
        
        # Уведомляем подписчиков об истечении кода
        await broadcast_expired_code(bot, code)
    else:
        await message.answer(
            f"❌ <b>Ошибка!</b>\n\n"
            f"Активный код <code>{code}</code> не найден.",
            parse_mode="HTML"
        )
    
    await state.clear()

@router.callback_query(lambda c: c.data == "admin_stats", AdminFilter())
async def admin_stats_callback(callback: CallbackQuery):
    """Показать статистику бота"""
    try:
        # Получаем количество активных кодов
        active_codes = await db.get_active_codes()
        active_count = len(active_codes)
        
        # Получаем количество подписчиков
        subscribers = await db.get_all_subscribers()
        subscriber_count = len(subscribers)
        
        stats_text = f"""
📊 <b>Статистика бота</b>

🎁 <b>Активные промо-коды:</b> {active_count}
👥 <b>Подписчики:</b> {subscriber_count}
📅 <b>Дата обновления:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}

<b>Активные коды:</b>
"""
        
        if active_codes:
            for code in active_codes:
                created = code.created_at.strftime('%d.%m') if code.created_at else 'N/A'
                stats_text += f"• <code>{code.code}</code> (добавлен {created})\n"
        else:
            stats_text += "Нет активных кодов\n"
        
        await callback.message.edit_text(
            stats_text,
            parse_mode="HTML",
            reply_markup=get_admin_keyboard()
        )
    
    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {e}")
        await callback.message.edit_text(
            "❌ Ошибка при получении статистики",
            reply_markup=get_admin_keyboard()
        )
    
    await callback.answer()

@router.callback_query(lambda c: c.data == "admin_active_codes", AdminFilter())
async def admin_active_codes_callback(callback: CallbackQuery):
    """Показать все активные коды"""
    codes = await db.get_active_codes()
    
    if not codes:
        await callback.message.edit_text(
            "🤷‍♂️ <b>Активных промо-кодов пока нет</b>",
            parse_mode="HTML",
            reply_markup=get_admin_keyboard()
        )
        await callback.answer()
        return
    
    codes_text = f"📋 <b>Активные промо-коды ({len(codes)}):</b>\n\n"
    
    for code in codes:
        created = code.created_at.strftime('%d.%m.%Y %H:%M') if code.created_at else 'N/A'
        codes_text += f"""
🔥 <b>{code.code}</b>
📝 {code.description}
💎 {code.rewards}
⏰ Добавлен: {created}
━━━━━━━━━━━━━━━━━━━
"""
    
    await callback.message.edit_text(
        codes_text,
        parse_mode="HTML",
        reply_markup=get_admin_keyboard()
    )
    await callback.answer()

async def broadcast_new_code(bot: Bot, code: CodeModel):
    """Рассылка нового кода всем подписчикам"""
    subscribers = await db.get_all_subscribers()
    
    if not subscribers:
        logger.info("Нет подписчиков для рассылки")
        return
    
    broadcast_text = f"""
🎉 <b>НОВЫЙ ПРОМО-КОД GENSHIN IMPACT!</b>

🔥 <b>Код:</b> <code>{code.code}</code>

💎 <b>Награды:</b> {code.rewards}

📝 <b>Описание:</b> {code.description}

⚡ <b>Активируй быстрее!</b> Промо-коды имеют ограниченное время действия.

💡 <i>Нажми кнопку ниже для мгновенной активации!</i>
"""
    
    successful_sends = 0
    failed_sends = 0
    
    for user_id in subscribers:
        try:
            await bot.send_message(
                chat_id=user_id,
                text=broadcast_text,
                parse_mode="HTML",
                reply_markup=get_code_activation_keyboard(code.code)
            )
            successful_sends += 1
            # Небольшая задержка, чтобы не превысить лимиты API
            await asyncio.sleep(0.05)
        except Exception as e:
            logger.warning(f"Не удалось отправить сообщение пользователю {user_id}: {e}")
            failed_sends += 1
    
    logger.info(f"Рассылка завершена: {successful_sends} успешно, {failed_sends} неудачно")

async def broadcast_expired_code(bot: Bot, code: str):
    """Уведомление об истечении кода"""
    subscribers = await db.get_all_subscribers()
    
    if not subscribers:
        return
    
    expired_text = f"""
⏰ <b>ПРОМО-КОД ИСТЕК</b>

❌ Код <code>{code}</code> больше не активен.

🔔 Следи за уведомлениями, чтобы не пропустить новые коды!
"""
    
    for user_id in subscribers:
        try:
            await bot.send_message(
                chat_id=user_id,
                text=expired_text,
                parse_mode="HTML"
            )
            await asyncio.sleep(0.05)
        except Exception as e:
            logger.warning(f"Не удалось отправить уведомление об истечении пользователю {user_id}: {e}")

# Команда для отмены текущего действия
@router.message(Command("cancel"), AdminFilter())
async def cancel_admin_action(message: Message, state: FSMContext):
    """Отмена текущего админ-действия"""
    await state.clear()
    await message.answer(
        "❌ <b>Действие отменено</b>",
        parse_mode="HTML",
        reply_markup=get_admin_keyboard()
    )