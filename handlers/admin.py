from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, PhotoSize, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

from database import db
from models import CodeModel
from filters.admin_filter import AdminFilter
from keyboards.inline import (
    get_admin_keyboard, get_code_activation_keyboard, 
    get_database_admin_keyboard, get_custom_post_keyboard,
    get_custom_post_with_button_keyboard, get_admin_stats_keyboard,
    get_admin_codes_keyboard, get_admin_users_keyboard,
    get_admin_add_code_keyboard, get_admin_expire_code_keyboard,
    get_admin_custom_post_keyboard
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
        current_text = callback.message.text or callback.message.caption or ""
        current_hash = get_content_hash(current_text)
        new_hash = get_content_hash(new_text)
        
        if current_hash == new_hash:
            await callback.answer("ℹ️ Данные актуальны", show_alert=False)
            return True
        
        await callback.message.edit_text(new_text, parse_mode=parse_mode, reply_markup=reply_markup)
        await callback.answer("✅ Обновлено", show_alert=False)
        return True
        
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            await callback.answer("ℹ️ Данные актуальны", show_alert=False)
            return True
        else:
            logger.error(f"Ошибка Telegram при редактировании сообщения: {e}")
            await callback.answer("❌ Ошибка обновления", show_alert=True)
            return False
    except Exception as e:
        logger.error(f"Неожиданная ошибка при редактировании сообщения: {e}")
        await callback.answer("❌ Ошибка обновления", show_alert=True)
        return False

async def broadcast_new_code(bot: Bot, code: CodeModel):
    """Рассылка нового кода всем подписчикам"""
    logger.info(f"Начинаю рассылку нового кода: {code.code}")
    
    try:
        subscribers = await db.get_all_subscribers()
        logger.info(f"Найдено подписчиков: {len(subscribers)}")
        
        if not subscribers:
            logger.warning("Нет подписчиков для рассылки")
            return
        
        # Формируем текст сообщения
        code_text = f"""
🎉 <b>Новый промо-код Genshin Impact!</b>

🔥 <b>Код:</b> <code>{code.code}</code>

💎 <b>Награды:</b> {code.rewards or 'Не указано'}

📝 <b>Описание:</b> {code.description or 'Промо-код Genshin Impact'}
"""
        
        if code.expires_date:
            code_text += f"\n⏰ <b>Действует до:</b> {format_expiry_date(code.expires_date)}"
        
        code_text += "\n\n<i>💡 Нажми кнопку ниже для активации!</i>"
        
        keyboard = get_code_activation_keyboard(code.code)
        
        sent_count = 0
        failed_count = 0
        blocked_count = 0
        
        for user_id in subscribers:
            try:
                message = await bot.send_message(
                    chat_id=user_id,
                    text=code_text,
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
                
                # ОБНОВЛЕНО: Сохраняем код в текстовом виде для обновления
                await db.save_code_message(code.id, user_id, message.message_id, code.code)
                
                sent_count += 1
                await asyncio.sleep(0.05)
                
            except TelegramForbiddenError:
                blocked_count += 1
                logger.debug(f"Пользователь {user_id} заблокировал бота")
                
            except TelegramRetryAfter as e:
                logger.warning(f"Флуд-лимит: ждем {e.retry_after} секунд")
                await asyncio.sleep(e.retry_after)
                
                try:
                    message = await bot.send_message(
                        chat_id=user_id,
                        text=code_text,
                        parse_mode="HTML",
                        reply_markup=keyboard
                    )
                    await db.save_code_message(code.id, user_id, message.message_id, code.code)
                    sent_count += 1
                except Exception:
                    failed_count += 1
                    
            except Exception as e:
                failed_count += 1
                logger.error(f"Ошибка отправки пользователю {user_id}: {e}")
        
        logger.info(f"Рассылка завершена. Отправлено: {sent_count}, Ошибок: {failed_count}, Заблокировано: {blocked_count}")
        
    except Exception as e:
        logger.error(f"Критическая ошибка при рассылке кода: {e}")

async def update_expired_code_messages(bot: Bot, code: str, messages_to_update):
    """ИСПРАВЛЕНА: Обновление старых сообщений при истечении кода"""
    logger.info(f"Обновляю {len(messages_to_update)} сообщений для истекшего кода: {code}")
    
    if not messages_to_update:
        logger.info("Нет сообщений для обновления")
        return
    
    # Формируем текст для истекшего кода
    expired_text = f"""
⌛ <b>Промо-код истек</b>

❌ <b>Код:</b> <code>{code}</code>

<i>Этот промо-код больше не действует. Следи за новыми кодами!</i>
"""
    
    # Клавиатура с истекшим кодом
    keyboard = get_code_activation_keyboard(code, is_expired=True)
    
    updated_count = 0
    failed_count = 0
    
    for message_info in messages_to_update:
        try:
            await bot.edit_message_text(
                chat_id=message_info.user_id,
                message_id=message_info.message_id,
                text=expired_text,
                parse_mode="HTML",
                reply_markup=keyboard
            )
            updated_count += 1
            
            # Небольшая пауза между обновлениями
            await asyncio.sleep(0.05)
            
        except TelegramBadRequest as e:
            if "message is not modified" in str(e):
                # Сообщение уже обновлено
                updated_count += 1
            elif "message to edit not found" in str(e):
                # Сообщение удалено пользователем
                logger.debug(f"Сообщение {message_info.message_id} пользователя {message_info.user_id} удалено")
            else:
                failed_count += 1
                logger.error(f"Ошибка обновления сообщения {message_info.message_id}: {e}")
                
        except TelegramForbiddenError:
            # Пользователь заблокировал бота
            logger.debug(f"Пользователь {message_info.user_id} заблокировал бота")
            
        except TelegramRetryAfter as e:
            logger.warning(f"Флуд-лимит при обновлении: ждем {e.retry_after} секунд")
            await asyncio.sleep(e.retry_after)
            
            # Повторяем попытку
            try:
                await bot.edit_message_text(
                    chat_id=message_info.user_id,
                    message_id=message_info.message_id,
                    text=expired_text,
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
                updated_count += 1
            except Exception:
                failed_count += 1
                
        except Exception as e:
            failed_count += 1
            logger.error(f"Неожиданная ошибка при обновлении сообщения: {e}")
    
    logger.info(f"Обновление сообщений завершено. Обновлено: {updated_count}, Ошибок: {failed_count}")

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
        parse_mode="HTML",
        reply_markup=get_admin_add_code_keyboard()
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
        
        new_code = CodeModel(
            code=code,
            description=description,
            rewards=rewards,
            expires_date=expires_date
        )
        
        code_id = await db.add_code(new_code)
        
        if code_id:
            confirmation_text = (
                f"✅ <b>Код успешно добавлен!</b>\n\n"
                f"🔥 <b>Код:</b> <code>{code}</code>\n"
                f"📝 <b>Описание:</b> {description}\n"
                f"💎 <b>Награды:</b> {rewards}"
            )
            
            if expires_date:
                confirmation_text += f"\n⏰ <b>Истекает:</b> {format_expiry_date(expires_date)}"
            
            confirmation_text += "\n\n🚀 <b>Начинаю рассылку подписчикам...</b>"
            
            await message.answer(confirmation_text, parse_mode="HTML")
            
            new_code.id = code_id
            await broadcast_new_code(bot, new_code)
            
            subscribers = await db.get_all_subscribers()
            await message.answer(
                f"📬 <b>Рассылка завершена!</b>\n\n"
                f"Уведомления отправлены {len(subscribers)} подписчикам.",
                parse_mode="HTML"
            )
            
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
            "🤷‍♂️ <b>Нет активных кодов для деактивации</b>\n\n"
            "Добавь новые коды через главное меню админки.",
            parse_mode="HTML",
            reply_markup=get_admin_expire_code_keyboard()
        )
        await callback.answer()
        return
    
    codes_list = "\n".join([f"• <code>{code.code}</code>" for code in codes])
    
    await callback.message.edit_text(
        f"❌ <b>Деактивация промо-кода</b>\n\n"
        f"<b>Активные коды:</b>\n{codes_list}\n\n"
        f"Отправь код, который нужно деактивировать, или /cancel для отмены:",
        parse_mode="HTML",
        reply_markup=get_admin_expire_code_keyboard()
    )
    
    await state.set_state(AdminStates.waiting_for_code_to_expire)
    await callback.answer()

@router.message(AdminStates.waiting_for_code_to_expire, AdminFilter())
async def process_expire_code(message: Message, state: FSMContext, bot: Bot):
    """ИСПРАВЛЕНА: Обработка деактивации кода с обновлением сообщений"""
    if message.text == "/cancel":
        await message.answer("❌ Деактивация кода отменена")
        await state.clear()
        return
    
    code = message.text.strip().upper()
    
    # ИСПРАВЛЕНО: Теперь получаем как статус, так и сообщения для обновления
    success, messages_to_update = await db.expire_code(code)
    
    if success:
        await message.answer(
            f"✅ <b>Код удален!</b>\n\n"
            f"Код <code>{code}</code> полностью удален из базы данных.\n\n"
            f"🔄 <b>Обновляю {len(messages_to_update)} старых сообщений...</b>",
            parse_mode="HTML"
        )
        
        # Обновляем старые сообщения пользователей
        await update_expired_code_messages(bot, code, messages_to_update)
        
        await message.answer(
            f"✅ <b>Обновление завершено!</b>\n\n"
            f"Все старые сообщения с кодом <code>{code}</code> помечены как истекшие.",
            parse_mode="HTML"
        )
    else:
        await message.answer(
            f"❌ <b>Ошибка!</b>\n\n"
            f"Активный код <code>{code}</code> не найден.",
            parse_mode="HTML"
        )
    
    await state.clear()

# Остальные обработчики остаются без изменений...
# (Добавьте все остальные функции из предыдущего файла)

@router.callback_query(lambda c: c.data == "admin_back", AdminFilter())
async def admin_back_callback(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню админа"""
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
    
    await safe_edit_message(callback, admin_text, get_admin_keyboard())

@router.callback_query(lambda c: c.data == "expired_code")
async def expired_code_callback(callback: CallbackQuery):
    """Обработчик нажатий на истекшие коды"""
    await callback.answer(
        "⌛ Этот промо-код больше не действует. Следите за новыми кодами!",
        show_alert=True
    )