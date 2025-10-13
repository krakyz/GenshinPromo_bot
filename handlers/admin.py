"""
Админ-модуль с системой тройного клика для валидации критичных действий
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
from models import CodeModel, BroadcastStats
from filters.admin_filter import AdminFilter
from keyboards.inline import (
    get_admin_keyboard, get_admin_stats_keyboard, get_admin_codes_keyboard,
    get_admin_users_keyboard, get_database_admin_keyboard, get_admin_back_keyboard,
    get_admin_expire_codes_keyboard, get_expire_code_click_keyboard,
    get_reset_db_click_keyboard, get_custom_post_keyboard, get_custom_post_with_button_keyboard
)
from utils.date_utils import DateTimeUtils
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
        """Получает статистику для админ-панели БЕЗ списка кодов"""
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
    
    @staticmethod
    def codes_list_message(codes) -> str:
        """Сообщение со списком активных кодов"""
        if not codes:
            return """🤷‍♂️ <b>Активных промо-кодов пока нет</b>

Добавь новый код через главное меню админки."""
        
        text = f"📋 <b>Активные промо-коды ({len(codes)}):</b>\n\n"
        
        for code in codes:
            created = code.created_at.strftime('%d.%m.%Y %H:%M МСК') if code.created_at else 'N/A'
            expires = DateTimeUtils.format_expiry_date(code.expires_date) if code.expires_date else 'Не указано'
            
            text += f"""🔥 <b>{code.code}</b>
📝 {code.description or 'Не указано'}
💎 {code.rewards or 'Не указано'}
⏰ Добавлен: {created}
⌛ Истекает: {expires}
━━━━━━━━━━━━━━━━━━━

"""
        
        return text
    
    @staticmethod
    def users_info_message(total_users: int, subscribers_count: int, recent_users) -> str:
        """Сообщение с информацией о пользователях"""
        text = f"""👥 <b>Информация о пользователях</b>

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
                
                text += f"\n\n{status} <b>{name}</b> ({username})"
                text += f"\n   ID: <code>{user['user_id']}</code>"
                text += f"\n   Присоединился: {joined}"
        else:
            text += "\n\nПользователи не найдены"
        
        return text
    
    @staticmethod
    def database_info_message(stats) -> str:
        """Сообщение с информацией о БД"""
        return f"""🗄️ <b>Управление базой данных</b>

📊 <b>Статистика БД:</b>
• 👥 Пользователи: {stats.get('users', 0)}
• 🎁 Активных кодов: {stats.get('codes_active', 0)}
• 📨 Записей сообщений: {stats.get('messages', 0)}
• 💾 Размер файла: {stats.get('file_size', '0 KB')}

⚠️ <b>Доступные операции:</b>
• Скачать файл базы данных
• Сбросить БД (удалить коды и сообщения, сохранить пользователей)"""


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


# Статистика (БЕЗ списка кодов)
@router.callback_query(F.data == "admin_stats", AdminFilter())
async def admin_stats_callback(callback: CallbackQuery):
    """Показать статистику бота БЕЗ списка кодов"""
    try:
        stats = await AdminService.get_admin_stats()
        stats_text = MessageTemplates.stats_message(stats)
        
        await MessageUtils.safe_edit_message(
            callback, stats_text, get_admin_stats_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка получения статистики: {e}")
        await callback.answer("❌ Ошибка получения статистики", show_alert=True)


# Активные коды
@router.callback_query(F.data == "admin_active_codes", AdminFilter())
async def admin_active_codes_callback(callback: CallbackQuery):
    """Показать все активные коды"""
    try:
        codes = await db.get_active_codes()
        codes_text = MessageTemplates.codes_list_message(codes)
        
        await MessageUtils.safe_edit_message(
            callback, codes_text, get_admin_codes_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка получения активных кодов: {e}")
        await callback.answer("❌ Ошибка получения кодов", show_alert=True)


# Пользователи
@router.callback_query(F.data == "admin_users", AdminFilter())
async def admin_users_callback(callback: CallbackQuery):
    """Показать информацию о пользователях"""
    try:
        total_users, subscribers_count, recent_users = await db.get_user_stats()
        users_text = MessageTemplates.users_info_message(total_users, subscribers_count, recent_users)
        
        await MessageUtils.safe_edit_message(
            callback, users_text, get_admin_users_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка получения информации о пользователях: {e}")
        await callback.answer("❌ Ошибка получения пользователей", show_alert=True)


# База данных
@router.callback_query(F.data == "admin_database", AdminFilter())
async def admin_database_callback(callback: CallbackQuery):
    """Показать меню управления базой данных"""
    try:
        stats = await db.get_database_stats()
        db_text = MessageTemplates.database_info_message(stats)
        
        await MessageUtils.safe_edit_message(
            callback, db_text, get_database_admin_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка получения статистики БД: {e}")
        await callback.answer("❌ Ошибка получения статистики БД", show_alert=True)


# Скачивание БД
@router.callback_query(F.data == "admin_download_db", AdminFilter())
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
        
        file = FSInputFile(db.db_path, filename="genshin_codes.db")
        await callback.message.answer_document(
            document=file,
            caption="📥 <b>Файл базы данных</b>\n\nСкачан: " + 
                   DateTimeUtils.get_moscow_time().strftime('%d.%m.%Y %H:%M МСК'),
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


# Добавление кода
@router.callback_query(F.data == "admin_add_code", AdminFilter())
async def add_code_callback(callback: CallbackQuery, state: FSMContext):
    """Начать процесс добавления кода"""
    add_code_text = """➕ <b>Добавление нового промо-кода</b>

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

Или отправь /cancel для отмены"""

    await callback.message.edit_text(
        add_code_text,
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
        validation = await AdminService.validate_code_data(lines)
        
        if not validation['valid']:
            await message.answer(validation['error'], parse_mode="HTML")
            return
        
        # Создаем объект кода
        new_code = CodeModel(
            code=validation['code'],
            description=validation['description'],
            rewards=validation['rewards'],
            expires_date=validation['expires_date']
        )
        
        # Добавляем в базу данных
        code_id = await db.add_code(new_code)
        
        if code_id:
            # Формируем подтверждение
            confirmation_text = f"""✅ <b>Код успешно добавлен!</b>

🔥 <b>Код:</b> <code>{validation['code']}</code>
📝 <b>Описание:</b> {validation['description']}
💎 <b>Награды:</b> {validation['rewards']}"""
            
            if validation['expires_date']:
                confirmation_text += f"\n⏰ <b>Истекает:</b> {DateTimeUtils.format_expiry_date(validation['expires_date'])}"
            
            confirmation_text += "\n\n🚀 <b>Начинаю рассылку подписчикам...</b>"
            
            await message.answer(confirmation_text, parse_mode="HTML")
            
            # Обновляем ID и делаем рассылку
            new_code.id = code_id
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
                f"❌ <b>Ошибка!</b>\n\nКод <code>{validation['code']}</code> уже существует в базе данных.",
                parse_mode="HTML"
            )
    
    except Exception as e:
        logger.error(f"Ошибка при добавлении кода: {e}")
        await message.answer(
            "❌ <b>Произошла ошибка при добавлении кода</b>\n\nПроверь формат и попробуй еще раз.",
            parse_mode="HTML"
        )
    
    await state.clear()


# Деактивация кода с кнопками
@router.callback_query(F.data == "admin_expire_code", AdminFilter())
async def expire_code_callback(callback: CallbackQuery, state: FSMContext):
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


# Обработка кликов по кодам для деактивации (ТРОЙНОЙ КЛИК)
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
    
    else:
        message_text = f"Выбери код для деактивации:"
    
    await callback.message.edit_text(
        message_text,
        parse_mode="HTML",
        reply_markup=get_expire_code_click_keyboard(code, click_count)
    )
    
    await callback.answer("🔸 Клик засчитан" if click_count < 3 else "⚠️ Готов к деактивации!")


# Подтверждение деактивации кода (после 3 кликов)
@router.callback_query(lambda c: c.data and c.data.startswith("confirm_expire_"), AdminFilter())
async def confirm_expire_code(callback: CallbackQuery, bot: Bot):
    """Окончательная деактивация кода после тройного клика"""
    code = callback.data.replace("confirm_expire_", "")
    
    try:
        # Обновляем сообщения ПЕРЕД удалением кода
        await update_expired_code_messages(bot, code)
        
        # Удаляем код
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
            
            logger.info(f"Код {code} деактивирован администратором {callback.from_user.id}")
        else:
            await callback.message.edit_text(
                f"❌ <b>Ошибка деактивации!</b>\n\nКод <code>{code}</code> не найден в базе данных.",
                parse_mode="HTML",
                reply_markup=get_admin_back_keyboard()
            )
    
    except Exception as e:
        logger.error(f"Ошибка деактивации кода {code}: {e}")
        await callback.message.edit_text(
            f"❌ <b>Критическая ошибка!</b>\n\nНе удалось деактивировать код <code>{code}</code>.",
            parse_mode="HTML",
            reply_markup=get_admin_back_keyboard()
        )
    
    await callback.answer()


# Сброс БД с тройным кликом
@router.callback_query(F.data == "admin_reset_db", AdminFilter())
async def reset_db_callback(callback: CallbackQuery):
    """Начать процесс сброса БД с тройным кликом"""
    await callback.message.edit_text(
        """🗄️ <b>Сброс базы данных</b>

⚠️ <b>Это критичное действие!</b>

💡 <i>Нажми кнопку трижды для подтверждения</i>

🗑️ <b>Будет удалено:</b>
• Все промо-коды
• Все записи сообщений

💾 <b>Будет сохранено:</b>
• Все пользователи и подписчики""",
        parse_mode="HTML",
        reply_markup=get_reset_db_click_keyboard(0)
    )
    
    await callback.answer()


# Обработка кликов по кнопке сброса БД (ТРОЙНОЙ КЛИК)
@router.callback_query(lambda c: c.data and c.data.startswith("reset_click_"), AdminFilter())
async def reset_db_click_handler(callback: CallbackQuery):
    """Обработка кликов по кнопке сброса БД (тройной клик для валидации)"""
    click_count = int(callback.data.replace("reset_click_", ""))
    
    if click_count == 1:
        message_text = """🗄️ <b>Сброс базы данных</b>

🔸 <i>Нажми кнопку еще 2 раза для подтверждения</i>

⚠️ <b>Предупреждение:</b>
• Все промо-коды будут удалены
• Все связанные сообщения будут очищены
• Пользователи останутся в системе"""
    
    elif click_count == 2:
        message_text = """🗄️ <b>Сброс базы данных</b>

🔸🔸 <i>Нажми кнопку еще 1 раз для подтверждения</i>

❌ <b>ПОСЛЕДНЕЕ ПРЕДУПРЕЖДЕНИЕ:</b>
• Это действие НЕОБРАТИМО
• Все данные кодов будут потеряны
• Восстановить будет невозможно"""
    
    elif click_count >= 3:
        message_text = """❌ <b>ВНИМАНИЕ!</b>

База данных готова к сбросу!

🔸🔸🔸 <i>Нажми красную кнопку для окончательного сброса</i>

💀 <b>Все коды будут уничтожены навсегда!</b>"""
    
    await callback.message.edit_text(
        message_text,
        parse_mode="HTML",
        reply_markup=get_reset_db_click_keyboard(click_count)
    )
    
    await callback.answer("🔸 Клик засчитан" if click_count < 3 else "💀 База готова к сбросу!")


# Окончательный сброс БД (после 3 кликов)
@router.callback_query(F.data == "confirm_reset_db", AdminFilter())
async def confirm_reset_db(callback: CallbackQuery):
    """Окончательный сброс базы данных после тройного клика"""
    try:
        success = await db.reset_database()
        
        if success:
            await callback.message.edit_text(
                """✅ <b>База данных успешно сброшена!</b>

🗑️ <b>Удалено:</b>
• Все промо-коды
• Все записи сообщений

💾 <b>Сохранено:</b>
• Все пользователи и подписчики

🎯 Бот готов к работе с чистой базой данных.""",
                parse_mode="HTML",
                reply_markup=get_admin_back_keyboard()
            )
            logger.info(f"База данных сброшена администратором {callback.from_user.id}")
        else:
            await callback.message.edit_text(
                "❌ <b>Ошибка при сбросе базы данных!</b>\n\nПопробуйте еще раз или обратитесь к разработчику.",
                parse_mode="HTML",
                reply_markup=get_admin_back_keyboard()
            )
    
    except Exception as e:
        logger.error(f"Ошибка при сбросе БД: {e}")
        await callback.message.edit_text(
            f"❌ <b>Критическая ошибка при сбросе!</b>\n\nДетали: {str(e)}",
            parse_mode="HTML",
            reply_markup=get_admin_back_keyboard()
        )
    
    await callback.answer()


# Кастомный пост - ВОССТАНОВЛЕН ПОЛНОСТЬЮ
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
    """Обработка изображения для кастомного поста и немедленная отправка"""
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
        
        # Отправляем рассылку немедленно
        stats = await broadcast_custom_post(bot, data, image_file_id, message.from_user.id)
        
    except Exception as e:
        logger.error(f"Ошибка при создании поста: {e}")
        await message.answer(
            "❌ <b>Произошла ошибка при создании поста</b>\n\nПопробуй еще раз.",
            parse_mode="HTML"
        )
    
    await state.clear()


# Возврат в главное меню
@router.callback_query(F.data == "admin_back", AdminFilter())
async def admin_back_callback(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню админа"""
    await state.clear()
    
    welcome_text = MessageTemplates.welcome_message()
    
    await MessageUtils.safe_edit_message(
        callback, welcome_text, get_admin_keyboard()
    )


# Отмена действия
@router.message(Command("cancel"), AdminFilter())
async def cancel_admin_action(message: Message, state: FSMContext):
    """Отмена текущего админ-действия"""
    await state.clear()
    await message.answer(
        "❌ <b>Действие отменено</b>",
        parse_mode="HTML"
    )


# Обработчик истекших кодов
@router.callback_query(F.data == "expired_code")
async def expired_code_callback(callback: CallbackQuery):
    """Обработчик нажатий на истекшие коды"""
    await callback.answer(
        "⌛ Этот промо-код больше не действует. Следите за новыми кодами!",
        show_alert=True
    )