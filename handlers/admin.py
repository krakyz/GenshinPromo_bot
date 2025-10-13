from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, PhotoSize, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram import Bot

from database import db
from models import CodeModel
from filters.admin_filter import AdminFilter
from keyboards.inline import (
    get_admin_keyboard, get_code_activation_keyboard, 
    get_database_admin_keyboard, get_custom_post_keyboard,
    get_custom_post_with_button_keyboard
)
from utils.date_utils import parse_expiry_date, format_expiry_date
from datetime import datetime
import asyncio
import logging
import os
import aiosqlite
from typing import Optional

logger = logging.getLogger(__name__)

router = Router()

class AdminStates(StatesGroup):
    """Состояния для админ-панели"""
    waiting_for_code_data = State()
    waiting_for_code_to_expire = State()
    waiting_for_custom_post_data = State()
    waiting_for_custom_post_image = State()
    waiting_for_db_reset_confirmation = State()  # Новое состояние для подтверждения сброса

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
• Управление пользователями
• Создать рекламный пост
• Управление базой данных

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
        "Награды\n"
        "Дата истечения (необязательно)</code>\n\n"
        "<b>Пример без даты истечения:</b>\n"
        "<code>GENSHINGIFT\n"
        "Стандартный промо-код\n"
        "50 Примогемов + 3 Книги героя</code>\n\n"
        "<b>Пример с датой истечения:</b>\n"
        "<code>LIMITEDCODE\n"
        "Ограниченный промо-код\n"
        "100 Примогемов + 5 Книг героя\n"
        "15.10.2025 23:59</code>\n\n"
        "Формат даты: ДД.ММ.ГГГГ ЧЧ:ММ или ДД.ММ.ГГГГ\n\n"
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
                "3. Награды\n"
                "4. Дата истечения (необязательно)",
                parse_mode="HTML"
            )
            return
        
        code = lines[0].strip().upper()
        description = lines[1].strip()
        rewards = lines[2].strip()
        expires_date = None
        
        # Проверяем, указана ли дата истечения
        if len(lines) > 3:
            expires_date = parse_expiry_date(lines[3])
            if lines[3].strip() and not expires_date:
                await message.answer(
                    "❌ <b>Неверный формат даты!</b>\n\n"
                    "Используй формат:\n"
                    "• <code>15.10.2025 23:59</code> (с временем)\n"
                    "• <code>15.10.2025</code> (без времени, истечет в 23:59 МСК)",
                    parse_mode="HTML"
                )
                return
        
        # Создаем объект кода
        new_code = CodeModel(
            code=code,
            description=description,
            rewards=rewards,
            expires_date=expires_date
        )
        
        # Добавляем в базу данных
        code_id = await db.add_code(new_code)
        
        if code_id:
            # Формируем сообщение подтверждения
            confirmation_text = (
                f"✅ <b>Код успешно добавлен!</b>\n\n"
                f"🔥 <b>Код:</b> <code>{code}</code>\n"
                f"📝 <b>Описание:</b> {description}\n"
                f"💎 <b>Награды:</b> {rewards}"
            )
            
            if expires_date:
                confirmation_text += f"\n⏰ <b>Истекает:</b> {format_expiry_date(expires_date)}"
            
            await message.answer(confirmation_text, parse_mode="HTML")
            
            # Обновляем объект с ID для рассылки
            new_code.id = code_id
            
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

@router.callback_query(lambda c: c.data == "admin_database", AdminFilter())
async def admin_database_callback(callback: CallbackQuery):
    """Показать меню управления базой данных"""
    stats = await db.get_database_stats()
    
    db_text = f"""
🗄️ <b>Управление базой данных</b>

📊 <b>Статистика БД:</b>
• 👥 Пользователи: {stats.get('users', 0)}
• 🎁 Активных кодов: {stats.get('codes_active', 0)}
• 📨 Записей сообщений: {stats.get('messages', 0)}
• 💾 Размер файла: {stats.get('file_size', '0 KB')}

⚠️ <b>Доступные операции:</b>
• Скачать файл базы данных
• Сбросить БД (удалить коды и сообщения, сохранить пользователей)
"""
    
    await callback.message.edit_text(
        db_text,
        parse_mode="HTML",
        reply_markup=get_database_admin_keyboard()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "admin_download_db", AdminFilter())
async def download_db_callback(callback: CallbackQuery):
    """Отправить файл базы данных администратору"""
    try:
        if not os.path.exists(db.db_path):
            await callback.message.edit_text(
                "❌ <b>Файл базы данных не найден!</b>",
                parse_mode="HTML",
                reply_markup=get_database_admin_keyboard()
            )
            await callback.answer()
            return
        
        # Отправляем файл
        file = FSInputFile(db.db_path, filename="genshin_codes.db")
        await callback.message.answer_document(
            document=file,
            caption="📥 <b>Файл базы данных</b>\n\nСкачан: " + datetime.now().strftime('%d.%m.%Y %H:%M МСК'),
            parse_mode="HTML"
        )
        
        await callback.message.edit_text(
            "✅ <b>Файл базы данных отправлен!</b>",
            parse_mode="HTML",
            reply_markup=get_database_admin_keyboard()
        )
        
        logger.info(f"Файл БД отправлен администратору {callback.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка при отправке файла БД: {e}")
        await callback.message.edit_text(
            "❌ <b>Ошибка при отправке файла!</b>\n\n"
            f"Детали: {str(e)}",
            parse_mode="HTML",
            reply_markup=get_database_admin_keyboard()
        )
    
    await callback.answer()

@router.callback_query(lambda c: c.data == "admin_reset_db", AdminFilter())
async def reset_db_callback(callback: CallbackQuery, state: FSMContext):
    """Начать процесс сброса БД с подтверждением"""
    await callback.message.edit_text(
        "⚠️ <b>ВНИМАНИЕ!</b>\n\n"
        "Вы собираетесь сбросить базу данных!\n\n"
        "🗑️ <b>Будет удалено:</b>\n"
        "• Все промо-коды\n"
        "• Все записи сообщений\n\n"
        "💾 <b>Будет сохранено:</b>\n"
        "• Все пользователи и подписчики\n\n"
        "🔐 <b>Для подтверждения отправь команду:</b>\n"
        "<code>/confirm_reset_db</code>\n\n"
        "⏰ <i>Подтверждение действует только в течение 5 минут</i>\n\n"
        "Для отмены нажми 'Назад'",
        parse_mode="HTML",
        reply_markup=get_database_admin_keyboard()
    )
    
    # Устанавливаем состояние ожидания подтверждения
    await state.set_state(AdminStates.waiting_for_db_reset_confirmation)
    
    # Устанавливаем таймер на 5 минут
    await asyncio.sleep(300)  # 5 минут
    
    # Проверяем, не отменил ли пользователь операцию
    current_state = await state.get_state()
    if current_state == AdminStates.waiting_for_db_reset_confirmation:
        await state.clear()
        logger.info(f"Время подтверждения сброса БД истекло для админа {callback.from_user.id}")
    
    await callback.answer()

@router.message(Command("confirm_reset_db"), AdminFilter())
async def confirm_reset_db(message: Message, state: FSMContext):
    """Подтверждение сброса базы данных (ТОЛЬКО после входа в меню!)"""
    
    # Проверяем, находится ли админ в состоянии ожидания подтверждения
    current_state = await state.get_state()
    
    if current_state != AdminStates.waiting_for_db_reset_confirmation.state:
        await message.answer(
            "❌ <b>Команда недоступна!</b>\n\n"
            "Для сброса базы данных:\n"
            "1. Зайди в админ-панель (/admin)\n"
            "2. Выбери 'База данных'\n"
            "3. Нажми 'Сбросить БД'\n"
            "4. Только тогда используй эту команду",
            parse_mode="HTML"
        )
        return
    
    try:
        success = await db.reset_database()
        
        if success:
            await message.answer(
                "✅ <b>База данных успешно сброшена!</b>\n\n"
                "🗑️ <b>Удалено:</b>\n"
                "• Все промо-коды\n"
                "• Все записи сообщений\n\n"
                "💾 <b>Сохранено:</b>\n"
                "• Все пользователи и подписчики\n\n"
                "Бот готов к работе с чистой базой данных.",
                parse_mode="HTML",
                reply_markup=get_admin_keyboard()
            )
            logger.info(f"База данных сброшена администратором {message.from_user.id}")
        else:
            await message.answer(
                "❌ <b>Ошибка при сбросе базы данных!</b>\n\n"
                "Попробуйте еще раз или обратитесь к разработчику.",
                parse_mode="HTML"
            )
    
    except Exception as e:
        logger.error(f"Ошибка при сбросе БД: {e}")
        await message.answer(
            "❌ <b>Критическая ошибка при сбросе!</b>\n\n"
            f"Детали: {str(e)}",
            parse_mode="HTML"
        )
    
    # Очищаем состояние после выполнения
    await state.clear()

@router.callback_query(lambda c: c.data == "admin_back", AdminFilter())
async def admin_back_callback(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню админа"""
    # Очищаем любые активные состояния при возврате в главное меню
    await state.clear()
    
    await callback.message.edit_text(
        "🔧 <b>Админ-панель бота Genshin Impact кодов</b>\n\n"
        "👋 Привет, администратор!\n\n"
        "📊 <b>Доступные действия:</b>\n"
        "• Добавить новый промо-код\n"
        "• Деактивировать истекший код\n"
        "• Просмотреть статистику бота\n"
        "• Показать все активные коды\n"
        "• Управление пользователями\n"
        "• Создать рекламный пост\n"
        "• Управление базой данных\n\n"
        "Выбери действие из меню ниже:",
        parse_mode="HTML",
        reply_markup=get_admin_keyboard()
    )
    await callback.answer()

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

# Остальные обработчики админки (сокращенные для экономии места)
@router.callback_query(lambda c: c.data == "admin_stats", AdminFilter())
async def admin_stats_callback(callback: CallbackQuery):
    """Показать статистику бота"""
    try:
        active_codes = await db.get_active_codes()
        active_count = len(active_codes)
        
        total_users, subscribers_count, _ = await db.get_user_stats()
        
        stats_text = f"""
📊 <b>Статистика бота</b>

🎁 <b>Активные промо-коды:</b> {active_count}
👥 <b>Всего пользователей:</b> {total_users}
🔔 <b>Подписчики:</b> {subscribers_count}
📅 <b>Дата обновления:</b> {datetime.now().strftime('%d.%m.%Y %H:%M МСК')}

<b>Активные коды:</b>
"""
        
        if active_codes:
            for code in active_codes:
                created = code.created_at.strftime('%d.%m') if code.created_at else 'N/A'
                expires = format_expiry_date(code.expires_date) if code.expires_date else 'Не указано'
                stats_text += f"• <code>{code.code}</code> (добавлен {created}, истекает {expires})\n"
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

# Placeholder функции для совместимости (нужно добавить полные реализации)
async def broadcast_new_code(bot: Bot, code: CodeModel):
    """Placeholder - добавить полную реализацию"""
    pass

@router.callback_query(lambda c: c.data == "expired_code")
async def expired_code_callback(callback: CallbackQuery):
    """Обработчик нажатий на истекшие коды"""
    await callback.answer(
        "⌛ Этот промо-код больше не действует. Следите за новыми кодами!",
        show_alert=True
    )