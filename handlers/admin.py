"""
Исправленный модуль админки с рабочим обновлением сообщений
"""
import asyncio
import logging
import os
import hashlib
from typing import Optional, Dict, Any
from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, PhotoSize, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest

from database import db
from models import CodeModel
from filters.admin_filter import AdminFilter
from keyboards.inline import (
    get_admin_keyboard, get_admin_stats_keyboard, get_admin_codes_keyboard,
    get_admin_users_keyboard, get_database_admin_keyboard, get_admin_back_keyboard,
    get_admin_expire_codes_keyboard, get_expire_code_click_keyboard,
    get_reset_db_click_keyboard
)
from utils.date_utils import DateTimeUtils, parse_expiry_date, format_expiry_date
from utils.broadcast import broadcast_new_code, broadcast_custom_post, update_expired_code_messages

logger = logging.getLogger(__name__)
router = Router()


class AdminStates(StatesGroup):
    """Состояния FSM для админ-панели"""
    waiting_for_code_data = State()
    waiting_for_code_to_expire = State()
    waiting_for_custom_post_data = State()
    waiting_for_custom_post_image = State()
    waiting_for_db_reset_confirmation = State()


def get_content_hash(text: str) -> str:
    """Получить хеш контента для сравнения"""
    return hashlib.md5(text.encode()).hexdigest()


async def safe_edit_message(callback: CallbackQuery, new_text: str, reply_markup=None, parse_mode="HTML"):
    """Безопасное редактирование сообщения"""
    try:
        current_text = callback.message.text or callback.message.caption or ""
        
        current_hash = get_content_hash(current_text)
        new_hash = get_content_hash(new_text)
        
        if current_hash == new_hash:
            await callback.answer("ℹ️ Данные актуальны", show_alert=False)
            return True
        
        await callback.message.edit_text(
            new_text,
            parse_mode=parse_mode,
            reply_markup=reply_markup
        )
        await callback.answer("✅ Обновлено", show_alert=False)
        return True
        
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            await callback.answer("ℹ️ Данные актуальны", show_alert=False)
            return True
        else:
            logger.error(f"Ошибка Telegram при редактировании: {e}")
            await callback.answer("❌ Ошибка обновления", show_alert=True)
            return False
    except Exception as e:
        logger.error(f"Неожиданная ошибка при редактировании: {e}")
        await callback.answer("❌ Ошибка обновления", show_alert=True)
        return False


# Основные обработчики админки
@router.message(Command("admin"), AdminFilter())
async def admin_panel(message: Message):
    """Главная админ-панель"""
    admin_text = """🔧 <b>Админ-панель бота Genshin Impact кодов</b>

👋 Привет, администратор!

📊 <b>Доступные действия:</b>
• Добавить новый промо-код
• Деактивировать истекший код
• Просмотреть статистику бота
• Показать все активные коды
• Управление пользователями
• Создать рекламный пост
• Управление базой данных

Выбери действие из меню ниже:"""
    
    await message.answer(admin_text, parse_mode="HTML", reply_markup=get_admin_keyboard())


@router.callback_query(F.data == "admin_add_code", AdminFilter())
async def add_code_callback(callback: CallbackQuery, state: FSMContext):
    """Добавление нового кода"""
    await callback.message.edit_text(
        """➕ <b>Добавление нового промо-кода</b>

Отправь данные о промо-коде в следующем формате:

<code>КОД
Описание кода
Награды
Дата истечения (необязательно)</code>

<b>Пример без даты истечения:</b>
<code>GENSHINGIFT
Стандартный промо-код
50 Примогемов + 3 Книги героя</code>

<b>Пример с датой истечения:</b>
<code>LIMITEDCODE
Ограниченный промо-код
100 Примогемов + 5 Книг героя
15.10.2025 23:59</code>

Или отправь /cancel для отмены""",
        parse_mode="HTML",
        reply_markup=get_admin_back_keyboard()
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
                "❌ <b>Неверный формат!</b>\n\nНужно минимум 3 строки:\n1. Код\n2. Описание\n3. Награды\n4. Дата истечения (необязательно)",
                parse_mode="HTML"
            )
            return
        
        code = lines[0].strip().upper()
        description = lines[1].strip()
        rewards = lines[2].strip()
        expires_date = None
        
        # Валидация кода
        if not code or len(code) < 3:
            await message.answer("❌ <b>Код слишком короткий!</b>\n\nКод должен содержать минимум 3 символа.", parse_mode="HTML")
            return
        
        if len(code) > 20:
            await message.answer("❌ <b>Код слишком длинный!</b>\n\nКод не может содержать более 20 символов.", parse_mode="HTML")
            return
        
        # Парсинг даты
        if len(lines) > 3 and lines[3].strip():
            expires_date = parse_expiry_date(lines[3])
            if not expires_date:
                await message.answer(
                    "❌ <b>Неверный формат даты!</b>\n\nПримеры корректных форматов:\n• 15.10.2025 (до 23:59)\n• 15.10.2025 15:30 (до указанного времени)",
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
            # Обновляем ID в объекте
            new_code.id = code_id
            
            # Формируем подтверждение
            confirmation_text = f"""✅ <b>Код успешно добавлен!</b>

🔥 <b>Код:</b> <code>{code}</code>
📝 <b>Описание:</b> {description}
💎 <b>Награды:</b> {rewards}"""
            
            if expires_date:
                confirmation_text += f"\n⏰ <b>Истекает:</b> {format_expiry_date(expires_date)}"
            
            confirmation_text += "\n\n🚀 <b>Начинаю рассылку подписчикам...</b>"
            
            await message.answer(confirmation_text, parse_mode="HTML")
            
            # Выполняем рассылку
            stats = await broadcast_new_code(bot, new_code)
            
            # Отчет о рассылке
            await message.answer(
                f"""📬 <b>Рассылка завершена!</b>

📊 <b>Результат:</b>
• Отправлено: {stats['sent']}
• Ошибок: {stats['failed']}
• Заблокировано: {stats['blocked']}""",
                parse_mode="HTML"
            )
            
        else:
            await message.answer(
                f"❌ <b>Ошибка!</b>\n\nКод <code>{code}</code> уже существует в базе данных.",
                parse_mode="HTML"
            )
    
    except Exception as e:
        logger.error(f"Ошибка при добавлении кода: {e}")
        await message.answer(
            "❌ <b>Произошла ошибка при добавлении кода</b>\n\nПроверь формат и попробуй еще раз.",
            parse_mode="HTML"
        )
    
    await state.clear()


@router.callback_query(F.data == "admin_expire_code", AdminFilter())
async def expire_code_callback(callback: CallbackQuery):
    """Начать процесс деактивации кода с кнопками"""
    codes = await db.get_active_codes()
    
    if not codes:
        await callback.message.edit_text(
            "🤷‍♂️ <b>Нет активных кодов для деактивации</b>\n\nДобавь новые коды через главное меню админки.",
            parse_mode="HTML",
            reply_markup=get_admin_back_keyboard()
        )
        await callback.answer()
        return
    
    await callback.message.edit_text(
        f"""❌ <b>Деактивация промо-кода</b>

<b>Активных кодов: {len(codes)}</b>

💡 <i>Нажми на код трижды для подтверждения деактивации</i>

Выбери код для деактивации:""",
        parse_mode="HTML",
        reply_markup=get_admin_expire_codes_keyboard(codes)
    )
    
    await callback.answer()


# Обработка тройного клика для деактивации кода
@router.callback_query(lambda c: c.data and c.data.startswith("expire_code_"), AdminFilter())
async def expire_code_click_handler(callback: CallbackQuery):
    """Обработка кликов по кодам (тройной клик для валидации)"""
    parts = callback.data.split("_")
    code = parts[2]
    click_count = int(parts[3]) if len(parts) > 3 else 1
    
    if click_count == 1:
        message_text = f"""⚠️ <b>Деактивация кода: {code}</b>

🔸 <i>Нажми кнопку еще 2 раза для подтверждения</i>

🗑️ <b>Это действие:</b>
• Удалит код из базы данных
• Обновит все старые сообщения пользователей
• Сделает код неактивным навсегда"""
    
    elif click_count == 2:
        message_text = f"""⚠️ <b>Деактивация кода: {code}</b>

🔸🔸 <i>Нажми кнопку еще 1 раз для подтверждения</i>

🗑️ <b>Это действие необратимо!</b>
• Код будет полностью удален
• Все связанные сообщения обновятся
• Восстановить будет невозможно"""
    
    elif click_count >= 3:
        message_text = f"""❌ <b>ВНИМАНИЕ!</b>

Код <code>{code}</code> готов к деактивации!

🔸🔸🔸 <i>Нажми красную кнопку для окончательного удаления</i>"""
    
    await callback.message.edit_text(
        message_text,
        parse_mode="HTML",
        reply_markup=get_expire_code_click_keyboard(code, click_count)
    )
    
    await callback.answer("🔸 Клик засчитан" if click_count < 3 else "⚠️ Готов к деактивации!")


@router.callback_query(lambda c: c.data and c.data.startswith("confirm_expire_"), AdminFilter())
async def confirm_expire_code(callback: CallbackQuery, bot: Bot):
    """Окончательная деактивация кода после тройного клика"""
    code = callback.data.replace("confirm_expire_", "")
    
    try:
        logger.info(f"Админ {callback.from_user.id} деактивирует код {code}")
        
        # ПЕРВЫМ ДЕЛОМ обновляем сообщения пользователей
        await callback.message.edit_text(
            f"🔄 <b>Обновляю сообщения пользователей...</b>\n\nКод: <code>{code}</code>",
            parse_mode="HTML"
        )
        
        # Обновляем все сообщения с этим кодом
        await update_expired_code_messages(bot, code)
        
        await callback.message.edit_text(
            f"🗑️ <b>Удаляю код из базы данных...</b>\n\nКод: <code>{code}</code>",
            parse_mode="HTML"
        )
        
        # Только ПОСЛЕ обновления сообщений удаляем код
        success = await db.expire_code(code)
        
        if success:
            await callback.message.edit_text(
                f"""✅ <b>Код успешно деактивирован!</b>

🗑️ <b>Код:</b> <code>{code}</code>
🔄 <b>Старые сообщения:</b> Обновлены
📊 <b>Статус:</b> Полностью удален из базы данных""",
                parse_mode="HTML",
                reply_markup=get_admin_back_keyboard()
            )
            
            logger.info(f"Код {code} успешно деактивирован администратором {callback.from_user.id}")
        else:
            await callback.message.edit_text(
                f"❌ <b>Ошибка деактивации!</b>\n\nКод <code>{code}</code> не найден в базе данных.",
                parse_mode="HTML",
                reply_markup=get_admin_back_keyboard()
            )
    
    except Exception as e:
        logger.error(f"Критическая ошибка деактивации кода {code}: {e}")
        await callback.message.edit_text(
            f"❌ <b>Критическая ошибка!</b>\n\nНе удалось деактивировать код <code>{code}</code>.\nДетали: {str(e)}",
            parse_mode="HTML",
            reply_markup=get_admin_back_keyboard()
        )
    
    await callback.answer()


# Статистика
@router.callback_query(F.data == "admin_stats", AdminFilter())
async def admin_stats_callback(callback: CallbackQuery):
    """Показать статистику бота"""
    try:
        active_codes = await db.get_active_codes()
        total_users, subscribers_count, _ = await db.get_user_stats()
        
        stats_text = f"""📊 <b>Статистика бота</b>

🎁 <b>Активные промо-коды:</b> {len(active_codes)}
👥 <b>Всего пользователей:</b> {total_users}
🔔 <b>Подписчики:</b> {subscribers_count}
📅 <b>Обновлено:</b> {datetime.now().strftime('%d.%m.%Y %H:%M МСК')}

💡 <i>Для просмотра кодов используй раздел "Активные коды"</i>"""
        
        await safe_edit_message(callback, stats_text, get_admin_stats_keyboard())
        
    except Exception as e:
        logger.error(f"Ошибка получения статистики: {e}")
        await callback.answer("❌ Ошибка получения статистики", show_alert=True)


# Активные коды
@router.callback_query(F.data == "admin_active_codes", AdminFilter())
async def admin_active_codes_callback(callback: CallbackQuery):
    """Показать все активные коды"""
    try:
        codes = await db.get_active_codes()
        
        if not codes:
            codes_text = """🤷‍♂️ <b>Активных промо-кодов пока нет</b>

Добавь новый код через главное меню админки."""
        else:
            codes_text = f"📋 <b>Активные промо-коды ({len(codes)}):</b>\n\n"
            
            for code in codes:
                created = code.created_at.strftime('%d.%m.%Y %H:%M МСК') if code.created_at else 'N/A'
                expires = format_expiry_date(code.expires_date) if code.expires_date else 'Не указано'
                
                codes_text += f"""🔥 <b>{code.code}</b>
📝 {code.description or 'Не указано'}
💎 {code.rewards or 'Не указано'}
⏰ Добавлен: {created}
⌛ Истекает: {expires}
━━━━━━━━━━━━━━━━━━━

"""
        
        await safe_edit_message(callback, codes_text, get_admin_codes_keyboard())
        
    except Exception as e:
        logger.error(f"Ошибка получения активных кодов: {e}")
        await callback.answer("❌ Ошибка получения кодов", show_alert=True)


# Остальные обработчики (пользователи, база данных, кастомные посты...)
@router.callback_query(F.data == "admin_users", AdminFilter())
async def admin_users_callback(callback: CallbackQuery):
    """Показать информацию о пользователях"""
    try:
        total_users, subscribers_count, recent_users = await db.get_user_stats()
        
        users_text = f"""👥 <b>Информация о пользователях</b>

📈 <b>Общая статистика:</b>
• Всего пользователей: {total_users}
• Подписчиков: {subscribers_count}
• Отписавшихся: {total_users - subscribers_count}
• Процент подписок: {round(subscribers_count/total_users*100, 1) if total_users > 0 else 0}%

👤 <b>Последние 5 пользователей:</b>"""
        
        if recent_users:
            for user in recent_users:
                name = user['first_name'] or 'Без имени'
                username = f"@{user['username']}" if user['username'] else 'Нет username'
                status = "🔔" if user['is_subscribed'] else "🔕"
                joined = user['joined_at'].strftime('%d.%m.%Y') if user['joined_at'] else 'N/A'
                
                users_text += f"\n\n{status} <b>{name}</b> ({username})"
                users_text += f"\n   ID: <code>{user['user_id']}</code>"
                users_text += f"\n   Присоединился: {joined}"
        else:
            users_text += "\n\nПользователи не найдены"
        
        await safe_edit_message(callback, users_text, get_admin_users_keyboard())
        
    except Exception as e:
        logger.error(f"Ошибка получения информации о пользователях: {e}")
        await callback.answer("❌ Ошибка получения пользователей", show_alert=True)


@router.callback_query(F.data == "admin_back", AdminFilter())
async def admin_back_callback(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню админа"""
    await state.clear()
    
    admin_text = """🔧 <b>Админ-панель бота Genshin Impact кодов</b>

👋 Привет, администратор!

📊 <b>Доступные действия:</b>
• Добавить новый промо-код
• Деактивировать истекший код
• Просмотреть статистику бота
• Показать все активные коды
• Управление пользователями
• Создать рекламный пост
• Управление базой данных

Выбери действие из меню ниже:"""
    
    await safe_edit_message(callback, admin_text, get_admin_keyboard())


@router.message(Command("cancel"), AdminFilter())
async def cancel_admin_action(message: Message, state: FSMContext):
    """Отмена текущего админ-действия"""
    await state.clear()
    await message.answer("❌ <b>Действие отменено</b>", parse_mode="HTML")


# Обработчик истекших кодов
@router.callback_query(F.data == "expired_code")
async def expired_code_callback(callback: CallbackQuery):
    """Обработчик нажатий на истекшие коды"""
    await callback.answer(
        "⌛ Этот промо-код больше не действует. Следите за новыми кодами!",
        show_alert=True
    )