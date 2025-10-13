"""
Исправленная система рассылки с принудительным сохранением связей сообщений
"""
import asyncio
import logging
from typing import List, Dict, Any, Optional
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

from database import db
from models import CodeModel
from keyboards.inline import get_code_activation_keyboard
from utils.date_utils import format_expiry_date

logger = logging.getLogger(__name__)


class BroadcastManager:
    """Управляет рассылкой сообщений с принудительным сохранением связей"""
    
    def __init__(self, bot: Bot, max_concurrent: int = 5, delay: float = 0.2):
        self.bot = bot
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.delay = delay
        self.stats = {"sent": 0, "failed": 0, "blocked": 0, "links_saved": 0}
    
    async def send_message_safe(
        self,
        user_id: int,
        text: str = None,
        photo: str = None,
        reply_markup=None,
        parse_mode: str = "HTML"
    ) -> Optional[int]:
        """Безопасная отправка сообщения одному пользователю. Возвращает message_id"""
        async with self.semaphore:
            try:
                if photo:
                    message = await self.bot.send_photo(
                        chat_id=user_id,
                        photo=photo,
                        caption=text,
                        reply_markup=reply_markup,
                        parse_mode=parse_mode
                    )
                else:
                    message = await self.bot.send_message(
                        chat_id=user_id,
                        text=text,
                        reply_markup=reply_markup,
                        parse_mode=parse_mode
                    )
                
                self.stats["sent"] += 1
                await asyncio.sleep(self.delay)
                return message.message_id
                
            except TelegramForbiddenError:
                self.stats["blocked"] += 1
                logger.debug(f"Пользователь {user_id} заблокировал бота")
                return None
                
            except TelegramRetryAfter as e:
                logger.warning(f"Флуд-лимит: ждем {e.retry_after} секунд")
                await asyncio.sleep(e.retry_after)
                return await self.send_message_safe(user_id, text, photo, reply_markup, parse_mode)
                
            except Exception as e:
                self.stats["failed"] += 1
                logger.error(f"Ошибка отправки пользователю {user_id}: {e}")
                return None
    
    async def save_message_link_safe(self, code_id: int, code_value: str, user_id: int, message_id: int) -> bool:
        """Безопасное сохранение связи сообщения с повторными попытками"""
        for attempt in range(3):
            try:
                success = await db.save_code_message(code_id, user_id, message_id, code_value)
                if success:
                    self.stats["links_saved"] += 1
                    logger.debug(f"✅ Связь сохранена: код={code_value}, пользователь={user_id}, сообщение={message_id}")
                    return True
                else:
                    logger.warning(f"⚠️ Не удалось сохранить связь для {user_id} (попытка {attempt + 1})")
                    
            except Exception as e:
                logger.error(f"❌ Ошибка сохранения связи для {user_id}: {e} (попытка {attempt + 1})")
                
            if attempt < 2:  # Не ждем после последней попытки
                await asyncio.sleep(0.1)
        
        return False


class MessageTemplates:
    """Шаблоны сообщений для различных типов рассылки"""
    
    @staticmethod
    def new_code_message(code: CodeModel) -> str:
        """Формирует сообщение о новом промо-коде"""
        text = f"""🎉 <b>Новый промо-код Genshin Impact!</b>

🔥 <b>Код:</b> <code>{code.code}</code>

💎 <b>Награды:</b> {code.rewards or 'Не указано'}

📝 <b>Описание:</b> {code.description or 'Промо-код Genshin Impact'}"""
        
        if code.expires_date:
            text += f"\n\n⏰ <b>Действует до:</b> {format_expiry_date(code.expires_date)}"
        
        text += "\n\n<i>💡 Нажми кнопку ниже для активации!</i>"
        return text
    
    @staticmethod
    def expired_code_message(code_value: str) -> str:
        """Формирует сообщение для истекшего кода"""
        return f"""❌ <b>Промо-код истек</b>

Код <code>{code_value}</code> больше недействителен.

🔔 <i>Подпишись на уведомления, чтобы не пропустить новые коды!</i>"""
    
    @staticmethod
    def custom_post_message(post_data: Dict[str, Any]) -> str:
        """Формирует кастомное сообщение"""
        return f"{post_data['title']}\n\n{post_data['text']}"


async def broadcast_new_code(bot: Bot, code: CodeModel) -> Dict[str, int]:
    """УЛУЧШЕННАЯ рассылка нового кода с гарантированным сохранением связей"""
    logger.info(f"🚀 Начинаю рассылку нового кода: {code.code} (ID: {code.id})")
    
    if not code.id:
        logger.error("❌ Код не имеет ID! Невозможно сохранить связи сообщений")
        return {"sent": 0, "failed": 0, "blocked": 0, "links_saved": 0}
    
    # Получаем подписчиков
    subscribers = await db.get_all_subscribers()
    if not subscribers:
        logger.warning("Нет подписчиков для рассылки")
        return {"sent": 0, "failed": 0, "blocked": 0, "links_saved": 0}
    
    logger.info(f"📊 Подписчиков для рассылки: {len(subscribers)}")
    
    # Подготавливаем сообщение и клавиатуру
    text = MessageTemplates.new_code_message(code)
    keyboard = get_code_activation_keyboard(code.code)
    
    # Создаем менеджер рассылки
    broadcast_manager = BroadcastManager(bot, max_concurrent=3, delay=0.3)
    
    # Отправляем сообщения и сохраняем связи пошагово
    successful_sends = []
    
    for i, user_id in enumerate(subscribers):
        logger.debug(f"📤 Отправляем код {code.code} пользователю {user_id} ({i+1}/{len(subscribers)})")
        
        # Отправляем сообщение
        message_id = await broadcast_manager.send_message_safe(
            user_id=user_id,
            text=text,
            reply_markup=keyboard
        )
        
        # Если отправка успешна, сразу сохраняем связь
        if message_id:
            link_saved = await broadcast_manager.save_message_link_safe(
                code_id=code.id,
                code_value=code.code,
                user_id=user_id,
                message_id=message_id
            )
            
            if link_saved:
                successful_sends.append({
                    'user_id': user_id,
                    'message_id': message_id,
                    'link_saved': True
                })
                logger.debug(f"✅ Пользователь {user_id}: отправлено + связь сохранена")
            else:
                successful_sends.append({
                    'user_id': user_id, 
                    'message_id': message_id,
                    'link_saved': False
                })
                logger.warning(f"⚠️ Пользователь {user_id}: отправлено, но связь НЕ сохранена!")
        
        # Каждые 10 сообщений выводим прогресс
        if (i + 1) % 10 == 0:
            logger.info(f"📊 Прогресс: {i+1}/{len(subscribers)} ({broadcast_manager.stats['sent']} отправлено, {broadcast_manager.stats['links_saved']} связей)")
    
    stats = broadcast_manager.stats
    
    logger.info(f"✅ Рассылка кода {code.code} завершена:")
    logger.info(f"   📤 Отправлено: {stats['sent']}")
    logger.info(f"   🔗 Связей сохранено: {stats['links_saved']}")
    logger.info(f"   ❌ Ошибок: {stats['failed']}")
    logger.info(f"   🚫 Заблокировано: {stats['blocked']}")
    
    # Дополнительная проверка связей в БД
    try:
        saved_messages = await db.get_code_messages_by_value(code.code)
        logger.info(f"🔍 Проверка БД: найдено {len(saved_messages)} связанных сообщений для кода {code.code}")
        
        if len(saved_messages) != stats['links_saved']:
            logger.warning(f"⚠️ Несоответствие: ожидалось {stats['links_saved']}, найдено {len(saved_messages)}")
    
    except Exception as e:
        logger.error(f"❌ Ошибка проверки связей в БД: {e}")
    
    return stats


async def update_expired_code_messages(bot: Bot, code_value: str):
    """УЛУЧШЕННАЯ функция обновления сообщений с детальным логированием"""
    logger.info(f"🔄 Начинаю обновление сообщений для кода: {code_value}")
    
    try:
        # Получаем все сообщения связанные с этим кодом
        messages = await db.get_code_messages_by_value(code_value)
        
        if not messages:
            logger.warning(f"⚠️ Сообщения для кода {code_value} не найдены в БД!")
            logger.info("💡 Возможные причины:")
            logger.info("   - Код добавлен до обновления системы")  
            logger.info("   - Связи не сохранились при рассылке")
            logger.info("   - Проблема с миграцией БД")
            return
        
        logger.info(f"📨 Найдено {len(messages)} сообщений для обновления")
        
        # Подготавливаем новые данные для истекшего кода
        expired_text = MessageTemplates.expired_code_message(code_value)
        expired_keyboard = get_code_activation_keyboard(code_value, is_expired=True)
        
        # Обновляем сообщения с детальным отслеживанием
        updated_count = 0
        failed_count = 0
        
        for i, msg in enumerate(messages):
            logger.debug(f"🔄 Обновляем сообщение {i+1}/{len(messages)}: пользователь {msg.user_id}, сообщение {msg.message_id}")
            
            try:
                await bot.edit_message_text(
                    chat_id=msg.user_id,
                    message_id=msg.message_id,
                    text=expired_text,
                    reply_markup=expired_keyboard,
                    parse_mode="HTML"
                )
                updated_count += 1
                logger.debug(f"✅ Обновлено сообщение у пользователя {msg.user_id}")
                
                # Пауза между обновлениями (избегаем лимитов)
                await asyncio.sleep(0.3)
                
            except TelegramBadRequest as e:
                failed_count += 1
                error_msg = str(e)
                if "message is not modified" in error_msg:
                    logger.debug(f"ℹ️ Сообщение у {msg.user_id} уже обновлено")
                elif "message to edit not found" in error_msg:
                    logger.debug(f"⚠️ Сообщение у {msg.user_id} удалено пользователем")
                else:
                    logger.warning(f"❌ Ошибка Telegram у {msg.user_id}: {error_msg}")
                continue
                
            except TelegramForbiddenError:
                failed_count += 1
                logger.debug(f"🚫 Пользователь {msg.user_id} заблокировал бота")
                continue
                
            except TelegramRetryAfter as e:
                logger.warning(f"⏳ Флуд-лимит: ждем {e.retry_after} секунд")
                await asyncio.sleep(e.retry_after)
                
                # Повторная попытка
                try:
                    await bot.edit_message_text(
                        chat_id=msg.user_id,
                        message_id=msg.message_id,
                        text=expired_text,
                        reply_markup=expired_keyboard,
                        parse_mode="HTML"
                    )
                    updated_count += 1
                    logger.debug(f"✅ Обновлено сообщение у пользователя {msg.user_id} (после повтора)")
                except:
                    failed_count += 1
                    logger.warning(f"❌ Повторная попытка не удалась для {msg.user_id}")
                    
            except Exception as e:
                failed_count += 1
                logger.error(f"❌ Неожиданная ошибка обновления сообщения {msg.id}: {e}")
            
            # Каждые 10 обновлений выводим прогресс
            if (i + 1) % 10 == 0:
                logger.info(f"📊 Прогресс обновления: {i+1}/{len(messages)} (обновлено: {updated_count}, ошибок: {failed_count})")
        
        logger.info(f"🎯 Обновление сообщений для кода {code_value} завершено:")
        logger.info(f"   ✅ Обновлено: {updated_count}")
        logger.info(f"   ❌ Ошибок: {failed_count}")
        logger.info(f"   📊 Успешность: {round(updated_count/len(messages)*100, 1) if len(messages) > 0 else 0}%")
        
    except Exception as e:
        logger.error(f"💥 Критическая ошибка при обновлении сообщений для кода {code_value}: {e}")
        import traceback
        traceback.print_exc()


async def broadcast_custom_post(
    bot: Bot,
    post_data: Dict[str, Any],
    image_file_id: Optional[str],
    admin_id: int
) -> Dict[str, int]:
    """Рассылка кастомного поста"""
    logger.info(f"📢 Начинаю рассылку поста: {post_data['title']}")
    
    # Получаем подписчиков
    subscribers = await db.get_all_subscribers()
    if not subscribers:
        logger.warning("Нет подписчиков для рассылки поста")
        return {"sent": 0, "failed": 0, "blocked": 0}
    
    # Подготавливаем сообщение и клавиатуру
    text = MessageTemplates.custom_post_message(post_data)
    
    # Клавиатура с кнопкой, если указана
    keyboard = None
    if post_data.get('button_text') and post_data.get('button_url'):
        from keyboards.inline import get_custom_post_with_button_keyboard
        keyboard = get_custom_post_with_button_keyboard(
            post_data['button_text'],
            post_data['button_url']
        )
    else:
        from keyboards.inline import get_custom_post_keyboard
        keyboard = get_custom_post_keyboard()
    
    # Выполняем рассылку
    broadcast_manager = BroadcastManager(bot, max_concurrent=3, delay=0.5)
    
    for user_id in subscribers:
        await broadcast_manager.send_message_safe(
            user_id=user_id,
            text=text,
            photo=image_file_id,
            reply_markup=keyboard
        )
    
    stats = broadcast_manager.stats
    
    # Отправляем отчет админу
    report_text = f"""✅ <b>Рассылка поста завершена!</b>

📊 <b>Результат:</b>
• 📤 Отправлено: {stats['sent']}
• ❌ Ошибок: {stats['failed']}
• 🚫 Заблокировано: {stats['blocked']}
• 👥 Всего подписчиков: {len(subscribers)}
• 📈 Успешность: {round(stats['sent']/len(subscribers)*100, 1) if len(subscribers) > 0 else 0}%"""

    try:
        await bot.send_message(chat_id=admin_id, text=report_text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка отправки отчета админу: {e}")
    
    logger.info(f"✅ Рассылка поста завершена: {stats}")
    return stats


# Тестовые функции для диагностики

async def test_code_message_links():
    """Тестирование связей сообщений в БД"""
    logger.info("🧪 Тестирование связей сообщений...")
    
    try:
        codes = await db.get_active_codes()
        logger.info(f"📊 Активных кодов: {len(codes)}")
        
        for code in codes:
            messages = await db.get_code_messages_by_value(code.code)
            logger.info(f"🎁 Код {code.code}: {len(messages)} связанных сообщений")
            
            if messages:
                for msg in messages[:3]:  # Показываем первые 3
                    logger.info(f"   - Пользователь: {msg.user_id}, Сообщение: {msg.message_id}")
    
    except Exception as e:
        logger.error(f"❌ Ошибка тестирования: {e}")


async def force_link_all_existing_messages():
    """Принудительное создание связей для существующих кодов (восстановление)"""
    logger.warning("⚠️ ВНИМАНИЕ: Принудительное создание связей для существующих кодов")
    logger.warning("Это создаст фиктивные связи для демонстрации работы обновления")
    
    try:
        codes = await db.get_active_codes()
        subscribers = await db.get_all_subscribers()
        
        if not codes or not subscribers:
            logger.info("Нет кодов или подписчиков для восстановления связей")
            return
        
        # Берем первый код для демонстрации
        test_code = codes[0]
        logger.info(f"🎯 Создаю демонстрационные связи для кода: {test_code.code}")
        
        # Создаем фиктивные связи (message_id = 999999 + user_id для уникальности)
        created_links = 0
        for user_id in subscribers[:5]:  # Только первые 5 для тестирования
            fake_message_id = 999999 + user_id  # Фиктивный ID сообщения
            
            success = await db.save_code_message(
                code_id=test_code.id,
                user_id=user_id,
                message_id=fake_message_id,
                code_value=test_code.code
            )
            
            if success:
                created_links += 1
        
        logger.info(f"✅ Создано {created_links} демонстрационных связей для кода {test_code.code}")
        logger.info("💡 Теперь можно протестировать деактивацию этого кода")
        
    except Exception as e:
        logger.error(f"❌ Ошибка восстановления связей: {e}")