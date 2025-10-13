from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, PhotoSize
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram import Bot

from database import db
from models import CodeModel, CustomPostModel
from filters.admin_filter import AdminFilter
from keyboards.inline import get_admin_keyboard, get_code_activation_keyboard, get_custom_post_keyboard
from datetime import datetime, timedelta
import asyncio
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

router = Router()

class AdminStates(StatesGroup):
    """Состояния для админ-панели"""
    waiting_for_code_data = State()
    waiting_for_code_to_expire = State()
    waiting_for_custom_post_data = State()
    waiting_for_custom_post_image = State()

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

def parse_expiry_date(date_str: str) -> Optional[datetime]:
    """Парсинг даты истечения из строки"""
    if not date_str.strip():
        return None
    
    try:
        date_str = date_str.strip()
        
        # Пробуем формат с временем: ДД.ММ.ГГГГ ЧЧ:ММ
        if len(date_str.split()) == 2:
            return datetime.strptime(date_str, "%d.%m.%Y %H:%M")
        
        # Пробуем формат без времени: ДД.ММ.ГГГГ (устанавливаем время на 23:59)
        elif len(date_str.split('.')) == 3:
            date_part = datetime.strptime(date_str, "%d.%m.%Y")
            return date_part.replace(hour=23, minute=59, second=59)
        
        return None
    except ValueError:
        return None

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
                    "• <code>15.10.2025</code> (без времени, истечет в 23:59)",
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
                confirmation_text += f"\n⏰ <b>Истекает:</b> {expires_date.strftime('%d.%m.%Y %H:%M')}"
            
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

@router.callback_query(lambda c: c.data == "admin_custom_post", AdminFilter())
async def custom_post_callback(callback: CallbackQuery, state: FSMContext):
    """Начать процесс создания кастомного поста"""
    await callback.message.edit_text(
        "📢 <b>Создание рекламного поста</b>\n\n"
        "Отправь данные для поста в следующем формате:\n\n"
        "<code>Заголовок\n"
        "Текст поста\n"
        "Текст кнопки (необязательно)\n"
        "Ссылка кнопки (необязательно)</code>\n\n"
        "<b>Пример без кнопки:</b>\n"
        "<code>🎮 Новость!\n"
        "Обновление 4.2 уже в игре!</code>\n\n"
        "<b>Пример с кнопкой:</b>\n"
        "<code>🛒 Магазин\n"
        "Скидки на примогемы!\n"
        "Купить сейчас\n"
        "https://example.com</code>\n\n"
        "Или отправь /cancel для отмены",
        parse_mode="HTML"
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
        if len(lines) < 2:
            await message.answer(
                "❌ <b>Неверный формат!</b>\n\n"
                "Нужно минимум 2 строки:\n"
                "1. Заголовок\n"
                "2. Текст поста",
                parse_mode="HTML"
            )
            return
        
        title = lines[0].strip()
        text = lines[1].strip()
        button_text = lines[2].strip() if len(lines) > 2 else None
        button_url = lines[3].strip() if len(lines) > 3 else None
        
        # Проверяем, что если указан текст кнопки, то указана и ссылка
        if button_text and not button_url:
            await message.answer(
                "❌ <b>Ошибка!</b>\n\n"
                "Если указан текст кнопки, необходимо также указать ссылку.",
                parse_mode="HTML"
            )
            return
        
        # Сохраняем данные в контексте
        await state.update_data({
            'title': title,
            'text': text,
            'button_text': button_text,
            'button_url': button_url
        })
        
        await message.answer(
            "📸 <b>Отлично!</b>\n\n"
            "Теперь отправь изображение для поста или отправь /skip чтобы создать пост без изображения.\n\n"
            "Или отправь /cancel для отмены.",
            parse_mode="HTML"
        )
        
        await state.set_state(AdminStates.waiting_for_custom_post_image)
    
    except Exception as e:
        logger.error(f"Ошибка при обработке данных поста: {e}")
        await message.answer(
            "❌ <b>Произошла ошибка при обработке данных</b>\n\n"
            "Проверь формат и попробуй еще раз.",
            parse_mode="HTML"
        )

@router.message(AdminStates.waiting_for_custom_post_image, AdminFilter())
async def process_custom_post_image(message: Message, state: FSMContext, bot: Bot):
    """Обработка изображения для кастомного поста"""
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
            "❌ <b>Неверный формат!</b>\n\n"
            "Отправь изображение или /skip для пропуска.",
            parse_mode="HTML"
        )
        return
    
    try:
        # Создаем объект поста
        custom_post = CustomPostModel(
            title=data['title'],
            text=data['text'],
            image_path=image_file_id,  # Сохраняем file_id как путь
            button_text=data.get('button_text'),
            button_url=data.get('button_url')
        )
        
        # Сохраняем в базу данных
        success = await db.add_custom_post(custom_post)
        
        if success:
            await message.answer(
                f"✅ <b>Пост создан успешно!</b>\n\n"
                f"📢 <b>Заголовок:</b> {custom_post.title}\n"
                f"📝 <b>Текст:</b> {custom_post.text}\n"
                f"📸 <b>Изображение:</b> {'Да' if image_file_id else 'Нет'}\n"
                f"🔗 <b>Кнопка:</b> {custom_post.button_text if custom_post.button_text else 'Нет'}\n\n"
                "🚀 <b>Начинаю рассылку...</b>",
                parse_mode="HTML"
            )
            
            # Отправляем рассылку
            await broadcast_custom_post(bot, custom_post, message.from_user.id)
            
        else:
            await message.answer(
                "❌ <b>Ошибка при сохранении поста</b>\n\n"
                "Попробуй еще раз.",
                parse_mode="HTML"
            )
    
    except Exception as e:
        logger.error(f"Ошибка при создании поста: {e}")
        await message.answer(
            "❌ <b>Произошла ошибка при создании поста</b>\n\n"
            "Попробуй еще раз.",
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
            f"Код <code>{code}</code> помечен как истекший.\n\n"
            f"🔄 <b>Обновляю сообщения пользователей...</b>",
            parse_mode="HTML"
        )
        
        # Обновляем старые сообщения вместо отправки новых
        await update_expired_code_messages(bot, code)
    else:
        await message.answer(
            f"❌ <b>Ошибка!</b>\n\n"
            f"Активный код <code>{code}</code> не найден.",
            parse_mode="HTML"
        )
    
    await state.clear()

# Остальные callback функции остаются прежними...
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
📅 <b>Дата обновления:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}

<b>Активные коды:</b>
"""
        
        if active_codes:
            for code in active_codes:
                created = code.created_at.strftime('%d.%m') if code.created_at else 'N/A'
                expires = code.expires_date.strftime('%d.%m %H:%M') if code.expires_date else 'Не указано'
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
        
        await callback.message.edit_text(
            users_text,
            parse_mode="HTML",
            reply_markup=get_admin_keyboard()
        )
    
    except Exception as e:
        logger.error(f"Ошибка при получении информации о пользователях: {e}")
        await callback.message.edit_text(
            "❌ Ошибка при получении информации о пользователях",
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
        expires = code.expires_date.strftime('%d.%m.%Y %H:%M') if code.expires_date else 'Не указано'
        codes_text += f"""
🔥 <b>{code.code}</b>
📝 {code.description}
💎 {code.rewards}
⏰ Добавлен: {created}
⌛ Истекает: {expires}
━━━━━━━━━━━━━━━━━━━
"""
    
    await callback.message.edit_text(
        codes_text,
        parse_mode="HTML",
        reply_markup=get_admin_keyboard()
    )
    await callback.answer()

async def broadcast_new_code(bot: Bot, code: CodeModel):
    """Рассылка нового кода всем подписчикам с сохранением message_id"""
    subscribers = await db.get_all_subscribers()
    
    if not subscribers:
        logger.info("Нет подписчиков для рассылки")
        return
    
    # Формируем текст сообщения
    broadcast_text = f"""
🎉 <b>НОВЫЙ ПРОМО-КОД GENSHIN IMPACT!</b>

🔥 <b>Код:</b> <code>{code.code}</code>

💎 <b>Награды:</b> {code.rewards}

📝 <b>Описание:</b> {code.description}
"""
    
    # Добавляем информацию о сроке истечения если она есть
    if code.expires_date:
        broadcast_text += f"\n⏰ <b>Действует до:</b> {code.expires_date.strftime('%d.%m.%Y %H:%M')}"
    
    broadcast_text += "\n\n⚡ <b>Активируй быстрее!</b> Промо-коды имеют ограниченное время действия.\n\n💡 <i>Нажми кнопку ниже для мгновенной активации!</i>"
    
    successful_sends = 0
    failed_sends = 0
    
    for user_id in subscribers:
        try:
            sent_message = await bot.send_message(
                chat_id=user_id,
                text=broadcast_text,
                parse_mode="HTML",
                reply_markup=get_code_activation_keyboard(code.code)
            )
            
            # Сохраняем связь между кодом и сообщением
            if code.id and sent_message.message_id:
                await db.save_code_message(code.id, user_id, sent_message.message_id)
            
            successful_sends += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            logger.warning(f"Не удалось отправить сообщение пользователю {user_id}: {e}")
            failed_sends += 1
    
    logger.info(f"Рассылка завершена: {successful_sends} успешно, {failed_sends} неудачно")

async def update_expired_code_messages(bot: Bot, code: str):
    """Обновление старых сообщений при истечении кода"""
    # Получаем ID кода по его строковому значению
    active_codes = await db.get_active_codes()
    expired_codes = []
    
    # Нам нужно получить также и истекшие коды для обновления
    async with db:
        async with aiosqlite.connect(db.db_path) as database:
            async with database.execute('''
                SELECT id, code, description, rewards, expires_date
                FROM codes
                WHERE code = ? AND is_active = 0
            ''', (code,)) as cursor:
                rows = await cursor.fetchall()
                if rows:
                    row = rows[0]
                    code_id = row[0]
                    code_obj = CodeModel(
                        id=row[0],
                        code=row[1],
                        description=row[2],
                        rewards=row[3],
                        expires_date=datetime.fromisoformat(row[4]) if row[4] else None
                    )
                else:
                    logger.warning(f"Код {code} не найден для обновления сообщений")
                    return
    
    # Получаем все сообщения связанные с этим кодом
    code_messages = await db.get_code_messages(code_id)
    
    if not code_messages:
        logger.info(f"Нет сообщений для обновления по коду {code}")
        return
    
    # Формируем обновленный текст
    expired_text = f"""
❌ <b>ПРОМО-КОД ИСТЕК</b>

🔥 <b>Код:</b> <code>{code_obj.code}</code>

💎 <b>Награды:</b> {code_obj.rewards}

📝 <b>Описание:</b> {code_obj.description}

⌛ <b>Этот код больше не действует</b>

💡 <i>Следи за уведомлениями, чтобы не пропустить новые коды!</i>
"""
    
    updated_count = 0
    failed_count = 0
    
    for message in code_messages:
        try:
            await bot.edit_message_text(
                chat_id=message.user_id,
                message_id=message.message_id,
                text=expired_text,
                parse_mode="HTML",
                reply_markup=get_code_activation_keyboard(code_obj.code, is_expired=True)
            )
            updated_count += 1
            await asyncio.sleep(0.03)  # Небольшая задержка
        except Exception as e:
            logger.warning(f"Не удалось обновить сообщение {message.message_id} для пользователя {message.user_id}: {e}")
            failed_count += 1
    
    logger.info(f"Обновление сообщений по коду {code}: {updated_count} успешно, {failed_count} неудачно")

async def broadcast_custom_post(bot: Bot, post: CustomPostModel, admin_id: int):
    """Рассылка кастомного поста всем подписчикам"""
    subscribers = await db.get_all_subscribers()
    
    if not subscribers:
        await bot.send_message(admin_id, "ℹ️ Нет подписчиков для рассылки")
        return
    
    # Формируем текст поста
    post_text = f"""
📢 <b>{post.title}</b>

{post.text}
"""
    
    successful_sends = 0
    failed_sends = 0
    
    for user_id in subscribers:
        try:
            # Определяем клавиатуру
            keyboard = get_custom_post_keyboard(post.button_text, post.button_url)
            
            if post.image_path:
                # Отправляем с изображением
                await bot.send_photo(
                    chat_id=user_id,
                    photo=post.image_path,
                    caption=post_text,
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
            else:
                # Отправляем только текст
                await bot.send_message(
                    chat_id=user_id,
                    text=post_text,
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
            
            successful_sends += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            logger.warning(f"Не удалось отправить пост пользователю {user_id}: {e}")
            failed_sends += 1
    
    # Уведомляем администратора о результатах
    result_text = f"""
✅ <b>Рассылка завершена!</b>

📊 <b>Результаты:</b>
• Успешно отправлено: {successful_sends}
• Ошибок: {failed_sends}
• Всего подписчиков: {len(subscribers)}

📢 <b>Пост:</b> "{post.title}"
"""
    
    await bot.send_message(admin_id, result_text, parse_mode="HTML")
    logger.info(f"Рассылка поста завершена: {successful_sends} успешно, {failed_sends} неудачно")

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

# Callback для обработки нажатий на истекшие коды
@router.callback_query(lambda c: c.data == "expired_code")
async def expired_code_callback(callback: CallbackQuery):
    """Обработчик нажатий на истекшие коды"""
    await callback.answer(
        "⌛ Этот промо-код больше не действует. Следите за новыми кодами!",
        show_alert=True
    )