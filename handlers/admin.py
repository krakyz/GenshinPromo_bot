"""
ИСПРАВЛЕННЫЙ админ-модуль с рабочим обновлением истекших сообщений
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
    get_reset_db_click_keyboard, get_custom_post_keyboard, get_custom_post_with_button_keyboard
)
from utils.date_utils import DateTimeUtils
# КРИТИЧНЫЙ ИМПОРТ: используем исправленные функции
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


class AdminService:
    """Сервис для админских операций"""
    
    @staticmethod
    async def get_admin_stats() -> Dict[str, Any]:
        """Получает статистику для админ-панели"""
        try:
            active_codes = await db.get_active_codes()
            total_users, subscribers_count, _ = await db.get_user_stats()
            
            return {
                'active_codes_count': len(active_codes),
                'total_users': total_users,
                'subscribers_count': subscribers_count,
                'updated_at': DateTimeUtils.get_moscow_time()
            }
        except Exception as e:
            logger.error(f"Ошибка получения админ статистики: {e}")
            return {}
    
    @staticmethod
    async def validate_code_data(lines: list) -> Dict[str, Any]:
        """Валидирует данные нового кода"""
        if len(lines) < 3:
            return {
                'valid': False,
                'error': "❌ <b>Неверный формат!</b>\n\nНужно минимум 3 строки:\n1. Код\n2. Описание\n3. Награды\n4. Дата истечения (необязательно)"
            }
        
        code = lines[0].strip().upper()
        description = lines[1].strip()
        rewards = lines[2].strip()
        expires_date = None
        
        # Валидация кода
        if not code or len(code) < 3:
            return {
                'valid': False,
                'error': "❌ <b>Код слишком короткий!</b>\n\nКод должен содержать минимум 3 символа."
            }
        
        if len(code) > 20:
            return {
                'valid': False,
                'error': "❌ <b>Код слишком длинный!</b>\n\nКод не может содержать более 20 символов."
            }
        
        # Парсинг даты
        if len(lines) > 3 and lines[3].strip():
            expires_date = DateTimeUtils.parse_expiry_date(lines[3])
            if not expires_date:
                return {
                    'valid': False,
                    'error': "❌ <b>Неверный формат даты!</b>\n\n" + DateTimeUtils.get_date_examples()
                }
        
        return {
            'valid': True,
            'code': code,
            'description': description,
            'rewards': rewards,
            'expires_date': expires_date
        }
    
    @staticmethod
    async def validate_custom_post_data(lines: list) -> Dict[str, Any]:
        """Валидирует данные кастомного поста"""
        if len(lines) < 2:
            return {
                'valid': False,
                'error': "❌ <b>Неверный формат!</b>\n\nНужно минимум 2 строки:\n1. Заголовок\n2. Текст поста"
            }
        
        title = lines[0].strip()
        text = lines[1].strip()
        button_text = lines[2].strip() if len(lines) > 2 else None
        button_url = lines[3].strip() if len(lines) > 3 else None
        
        # Проверяем, что если указан текст кнопки, то указана и ссылка
        if button_text and not button_url:
            return {
                'valid': False,
                'error': "❌ <b>Ошибка!</b>\n\nЕсли указан текст кнопки, необходимо также указать ссылку."
            }
        
        return {
            'valid': True,
            'title': title,
            'text': text,
            'button_text': button_text,
            'button_url': button_url
        }


class MessageUtils:
    """Утилиты для работы с сообщениями"""
    
    @staticmethod
    def get_content_hash(text: str) -> str:
        """Получить хеш контента для сравнения"""
        return hashlib.md5(text.encode()).hexdigest()
    
    @staticmethod
    async def safe_edit_message(
        callback: CallbackQuery,
        new_text: str,
        reply_markup=None,
        parse_mode: str = "HTML"
    ) -> bool:
        """Безопасное редактирование сообщения с проверкой изменений"""
        try:
            current_text = callback.message.text or callback.message.caption or ""
            
            current_hash = MessageUtils.get_content_hash(current_text)
            new_hash = MessageUtils.get_content_hash(new_text)
            
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


class MessageTemplates:
    """Шаблоны сообщений админ-панели"""
    
    @staticmethod
    def welcome_message() -> str:
        """Приветственное сообщение админ-панели"""
        return """🔧 <b>Админ-панель бота Genshin Impact кодов</b>

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
    
    @staticmethod
    def stats_message(stats: Dict[str, Any]) -> str:
        """Сообщение статистики БЕЗ списка кодов"""
        if not stats:
            return "❌ <b>Ошибка получения статистики</b>"
        
        text = f"""📊 <b>Статистика бота</b>

🎁 <b>Активные промо-коды:</b> {stats.get('active_codes_count', 0)}
👥 <b>Всего пользователей:</b> {stats.get('total_users', 0)}
🔔 <b>Подписчики:</b> {stats.get('subscribers_count', 0)}
📅 <b>Обновлено:</b> {stats.get('updated_at', datetime.now()).strftime('%d.%m.%Y %H:%M МСК')}

💡 <i>Для просмотра кодов используй раздел "Активные коды"</i>"""
        
        return text


# Основные обработчики
@router.message(Command("admin"), AdminFilter())
async def admin_panel(message: Message):
    """Главная админ-панель"""
    welcome_text = MessageTemplates.welcome_message()
    
    await message.answer(
        welcome_text,
        parse_mode="HTML",
        reply_markup=get_admin_keyboard()
    )


# ... (остальные обработчики админки остаются прежними)


# КРИТИЧНО: Исправленная деактивация кода с обновлением сообщений
@router.callback_query(lambda c: c.data and c.data.startswith("confirm_expire_"), AdminFilter())
async def confirm_expire_code(callback: CallbackQuery, bot: Bot):
    """ИСПРАВЛЕННОЕ окончательное удаление кода после тройного клика"""
    code = callback.data.replace("confirm_expire_", "")
    
    try:
        logger.info(f"Деактивация кода {code} администратором {callback.from_user.id}")
        
        # КРИТИЧНО: Обновляем сообщения ПЕРЕД удалением кода
        await callback.message.edit_text(
            f"""⏳ <b>Обновляю сообщения пользователей...</b>

Код: <code>{code}</code>

🔄 Поиск связанных сообщений...
📝 Обновление текста и кнопок...
⚠️ Пожалуйста подождите...""",
            parse_mode="HTML"
        )
        
        # Обновляем все старые сообщения пользователей
        await update_expired_code_messages(bot, code)
        
        await callback.message.edit_text(
            f"""⏳ <b>Удаляю код из базы данных...</b>

Код: <code>{code}</code>

✅ Сообщения обновлены
🗑️ Удаление из базы данных...""",
            parse_mode="HTML"
        )
        
        # Удаляем код из БД
        success = await db.expire_code(code)
        
        if success:
            await callback.message.edit_text(
                f"""✅ <b>Код успешно деактивирован!</b>

🗑️ <b>Код:</b> <code>{code}</code>
🔄 <b>Старые сообщения:</b> Обновлены ✅
📊 <b>Статус:</b> Полностью удален из базы данных ✅

<i>💡 Все пользователи увидят, что код больше не действует</i>""",
                parse_mode="HTML",
                reply_markup=get_admin_back_keyboard()
            )
            
            logger.info(f"✅ Код {code} успешно деактивирован с обновлением сообщений")
            
        else:
            await callback.message.edit_text(
                f"❌ <b>Ошибка деактивации!</b>\n\nКод <code>{code}</code> не найден в базе данных.",
                parse_mode="HTML",
                reply_markup=get_admin_back_keyboard()
            )
            logger.warning(f"⚠️ Код {code} не найден в БД")
    
    except Exception as e:
        logger.error(f"💥 Ошибка деактивации кода {code}: {e}")
        await callback.message.edit_text(
            f"""❌ <b>Критическая ошибка!</b>

Не удалось деактивировать код <code>{code}</code>

<b>Возможные причины:</b>
• Ошибка подключения к БД
• Код уже был удален
• Проблема с обновлением сообщений

<i>Попробуй еще раз или обратись к разработчику</i>""",
            parse_mode="HTML",
            reply_markup=get_admin_back_keyboard()
        )
    
    await callback.answer()


# Восстановленный кастомный пост
@router.callback_query(F.data == "admin_custom_post", AdminFilter())
async def custom_post_callback(callback: CallbackQuery, state: FSMContext):
    """Начать процесс создания кастомного поста"""
    await callback.message.edit_text(
        """📢 <b>Создание рекламного поста</b>

Отправь данные для поста в следующем формате:

<code>Заголовок
Текст поста
Текст кнопки (необязательно)
Ссылка кнопки (необязательно)</code>

<b>Пример без кнопки:</b>
<code>🎮 Новость!
Обновление 4.2 уже в игре!</code>

<b>Пример с кнопкой:</b>
<code>🛒 Магазин
Скидки на примогемы!
Купить сейчас
https://example.com</code>

Или отправь /cancel для отмены""",
        parse_mode="HTML",
        reply_markup=get_admin_back_keyboard()
    )
    
    await state.set_state(AdminStates.waiting_for_custom_post_data)
    await callback.answer()


@router.message(AdminStates.waiting_for_custom_post_data, AdminFilter())
async def process_custom_post_data(message: Message, state: FSMContext):
    """Обработка данных кастомного поста"""
    if message.text == "/cancel":
        await message.answer("❌ Создание поста отменено")
        await state.clear()
        return
    
    try:
        lines = message.text.strip().split('\n')
        validation = await AdminService.validate_custom_post_data(lines)
        
        if not validation['valid']:
            await message.answer(validation['error'], parse_mode="HTML")
            return
        
        # Сохраняем данные в контексте
        await state.update_data({
            'title': validation['title'],
            'text': validation['text'],
            'button_text': validation['button_text'],
            'button_url': validation['button_url']
        })
        
        await message.answer(
            """📸 <b>Отлично!</b>

Теперь отправь изображение для поста или отправь /skip чтобы создать пост без изображения.

Или отправь /cancel для отмены.""",
            parse_mode="HTML"
        )
        
        await state.set_state(AdminStates.waiting_for_custom_post_image)
    
    except Exception as e:
        logger.error(f"Ошибка при обработке данных поста: {e}")
        await message.answer(
            "❌ <b>Произошла ошибка при обработке данных</b>\n\nПроверь формат и попробуй еще раз.",
            parse_mode="HTML"
        )


@router.message(AdminStates.waiting_for_custom_post_image, AdminFilter())
async def process_custom_post_image(message: Message, state: FSMContext, bot: Bot):
    """Обработка изображения для кастомного поста и отправка"""
    if message.text == "/cancel":
        await message.answer("❌ Создание поста отменено")
        await state.clear()
        return
    
    data = await state.get_data()
    image_file_id = None
    
    # Проверяем, отправил ли пользователь изображение или команду skip
    if message.photo:
        # Получаем изображение наивысшего качества
        photo: PhotoSize = message.photo[-1]
        image_file_id = photo.file_id
        logger.info(f"Получено изображение для поста: {image_file_id}")
    elif message.text == "/skip":
        logger.info("Пост создается без изображения")
    else:
        await message.answer(
            "❌ <b>Неверный формат!</b>\n\nОтправь изображение или /skip для пропуска.",
            parse_mode="HTML"
        )
        return
    
    try:
        await message.answer(
            f"""✅ <b>Пост готов к отправке!</b>

📢 <b>Заголовок:</b> {data['title']}
📝 <b>Текст:</b> {data['text']}
📸 <b>Изображение:</b> {'Да' if image_file_id else 'Нет'}
🔗 <b>Кнопка:</b> {data.get('button_text') if data.get('button_text') else 'Нет'}

🚀 <b>Начинаю рассылку...</b>""",
            parse_mode="HTML"
        )
        
        # Отправляем рассылку
        stats = await broadcast_custom_post(bot, data, image_file_id, message.from_user.id)
        
    except Exception as e:
        logger.error(f"Ошибка при создании поста: {e}")
        await message.answer(
            "❌ <b>Произошла ошибка при создании поста</b>\n\nПопробуй еще раз.",
            parse_mode="HTML"
        )
    
    await state.clear()


# Обработчик истекших кодов
@router.callback_query(F.data == "expired_code")
async def expired_code_callback(callback: CallbackQuery):
    """Обработчик нажатий на истекшие коды"""
    await callback.answer(
        "⌛ Этот промо-код больше не действует. Следите за новыми кодами!",
        show_alert=True
    )