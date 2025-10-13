from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, PhotoSize, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from database import db
from models import CodeModel
from filters.admin_filter import AdminFilter
from keyboards.inline import (
    get_admin_keyboard, get_code_activation_keyboard, 
    get_database_admin_keyboard, get_custom_post_keyboard,
    get_custom_post_with_button_keyboard, get_admin_stats_keyboard,
    get_admin_codes_keyboard, get_admin_users_keyboard
)
from utils.date_utils import parse_expiry_date, format_expiry_date
from datetime import datetime
import asyncio
import logging
import os
import aiosqlite
from typing import Optional
import hashlib

logger = logging.getLogger(__name__)

router = Router()

class AdminStates(StatesGroup):
    """Состояния для админ-панели"""
    waiting_for_code_data = State()
    waiting_for_code_to_expire = State()
    waiting_for_custom_post_data = State()
    waiting_for_custom_post_image = State()
    waiting_for_db_reset_confirmation = State()

def get_content_hash(text: str) -> str:
    """Получить хеш контента для сравнения"""
    return hashlib.md5(text.encode()).hexdigest()

async def safe_edit_message(callback: CallbackQuery, new_text: str, reply_markup=None, parse_mode="HTML"):
    """Безопасное редактирование сообщения с проверкой изменений"""
    try:
        # Получаем текущий текст сообщения (без HTML разметки для сравнения)
        current_text = callback.message.text or callback.message.caption or ""
        
        # Сравниваем хеши контента
        current_hash = get_content_hash(current_text)
        new_hash = get_content_hash(new_text)
        
        if current_hash == new_hash:
            # Контент не изменился, просто отвечаем на callback
            await callback.answer("ℹ️ Данные актуальны", show_alert=False)
            return True
        
        # Контент изменился, обновляем сообщение
        await callback.message.edit_text(
            new_text,
            parse_mode=parse_mode,
            reply_markup=reply_markup
        )
        await callback.answer("✅ Обновлено", show_alert=False)
        return True
        
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            # Telegram считает что сообщение не изменилось
            await callback.answer("ℹ️ Данные актуальны", show_alert=False)
            return True
        else:
            # Другая ошибка Telegram
            logger.error(f"Ошибка Telegram при редактировании сообщения: {e}")
            await callback.answer("❌ Ошибка обновления", show_alert=True)
            return False
    except Exception as e:
        # Неожиданная ошибка
        logger.error(f"Неожиданная ошибка при редактировании сообщения: {e}")
        await callback.answer("❌ Ошибка обновления", show_alert=True)
        return False

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
📅 <b>Обновлено:</b> {datetime.now().strftime('%d.%m.%Y %H:%M МСК')}

<b>Активные коды:</b>
"""
        
        if active_codes:
            for code in active_codes:
                created = code.created_at.strftime('%d.%m') if code.created_at else 'N/A'
                expires = format_expiry_date(code.expires_date) if code.expires_date else 'Не указано'
                stats_text += f"• <code>{code.code}</code> (добавлен {created}, истекает {expires})\n"
        else:
            stats_text += "Нет активных кодов\n"
        
        # Используем безопасное редактирование
        await safe_edit_message(callback, stats_text, get_admin_stats_keyboard())
    
    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {e}")
        await callback.answer("❌ Ошибка получения статистики", show_alert=True)

@router.callback_query(lambda c: c.data == "admin_active_codes", AdminFilter())
async def admin_active_codes_callback(callback: CallbackQuery):
    """Показать все активные коды"""
    try:
        codes = await db.get_active_codes()
        
        if not codes:
            codes_text = (
                "🤷‍♂️ <b>Активных промо-кодов пока нет</b>\n\n"
                "Добавь новый код через главное меню админки."
            )
        else:
            codes_text = f"📋 <b>Активные промо-коды ({len(codes)}):</b>\n\n"
            
            for code in codes:
                created = code.created_at.strftime('%d.%m.%Y %H:%M МСК') if code.created_at else 'N/A'
                expires = format_expiry_date(code.expires_date) if code.expires_date else 'Не указано'
                codes_text += f"""
🔥 <b>{code.code}</b>
📝 {code.description}
💎 {code.rewards}
⏰ Добавлен: {created}
⌛ Истекает: {expires}
━━━━━━━━━━━━━━━━━━━
"""
        
        # Используем безопасное редактирование
        await safe_edit_message(callback, codes_text, get_admin_codes_keyboard())
    
    except Exception as e:
        logger.error(f"Ошибка при получении активных кодов: {e}")
        await callback.answer("❌ Ошибка получения кодов", show_alert=True)

@router.callback_query(lambda c: c.data == "admin_users", AdminFilter())
async def admin_users_callback(callback: CallbackQuery):
    """Показать информацию о пользователях"""
    try:
        total_users, subscribers_count, recent_users = await db.get_user_stats()
        
        users_text = f"""
👥 <b>Информация о пользователях</b>

📈 <b>Общая статистика:</b>
• Всего пользователей: {total_users}
• Подписчиков: {subscribers_count}
• Отписавшихся: {total_users - subscribers_count}
• Процент подписок: {round(subscribers_count/total_users*100, 1) if total_users > 0 else 0}%

👤 <b>Последние 5 пользователей:</b>
"""
        
        if recent_users:
            for user in recent_users:
                name = user['first_name'] or 'Без имени'
                username = f"@{user['username']}" if user['username'] else 'Нет username'
                status = "🔔" if user['is_subscribed'] else "🔕"
                joined = user['joined_at'].strftime('%d.%m.%Y') if user['joined_at'] else 'N/A'
                
                users_text += f"\n{status} <b>{name}</b> ({username})\n"
                users_text += f"   ID: <code>{user['user_id']}</code>\n"
                users_text += f"   Присоединился: {joined}\n"
        else:
            users_text += "\nПользователи не найдены"
        
        # Используем безопасное редактирование
        await safe_edit_message(callback, users_text, get_admin_users_keyboard())
    
    except Exception as e:
        logger.error(f"Ошибка при получении информации о пользователях: {e}")
        await callback.answer("❌ Ошибка получения пользователей", show_alert=True)

@router.callback_query(lambda c: c.data == "admin_database", AdminFilter())
async def admin_database_callback(callback: CallbackQuery):
    """Показать меню управления базой данных"""
    try:
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
        
        # Используем безопасное редактирование
        await safe_edit_message(callback, db_text, get_database_admin_keyboard())
    
    except Exception as e:
        logger.error(f"Ошибка при получении статистики БД: {e}")
        await callback.answer("❌ Ошибка получения статистики БД", show_alert=True)

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
        await callback.answer("❌ Ошибка отправки файла", show_alert=True)
    
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
    
    # Используем безопасное редактирование
    await safe_edit_message(callback, admin_text, get_admin_keyboard())

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

# Placeholder функции (добавить полные реализации из других файлов)
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