class BroadcastManager:
    """Управляет рассылкой сообщений с оптимизацией"""
    
    def __init__(self, bot: Bot, max_concurrent: int = 10, delay: float = 0.05):
        self.bot = bot
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.delay = delay
        self.stats = {"sent": 0, "failed": 0, "blocked": 0}
        self.sent_messages = []  # Для хранения отправленных сообщений
    
    async def send_message_safe(
        self,
        user_id: int,
        text: str = None,
        photo: str = None,
        reply_markup=None,
        parse_mode: str = "HTML"
    ) -> Optional[int]:
        """Безопасная отправка сообщения одному пользователю с возвратом message_id"""
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
                # Сохраняем информацию об отправленном сообщении
                self.sent_messages.append({
                    'user_id': user_id,
                    'message_id': message.message_id
                })
                
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
    
    async def broadcast_to_users(
        self,
        user_ids: List[int],
        text: str = None,
        photo: str = None,
        reply_markup=None
    ) -> Dict[str, Any]:
        """Рассылка сообщений списку пользователей"""
        self.stats = {"sent": 0, "failed": 0, "blocked": 0}
        self.sent_messages = []
        
        tasks = [
            self.send_message_safe(user_id, text, photo, reply_markup)
            for user_id in user_ids
        ]
        
        await asyncio.gather(*tasks, return_exceptions=True)
        return {
            'stats': self.stats.copy(),
            'messages': self.sent_messages.copy()
        }


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
    
    @staticmethod
    def broadcast_report(stats: Dict[str, int], total_subscribers: int) -> str:
        """Формирует отчет о рассылке"""
        return f"""✅ <b>Рассылка завершена!</b>

📊 <b>Статистика:</b>
• 📤 Отправлено: {stats['sent']}
• ❌ Ошибок: {stats['failed']}
• 🚫 Заблокировано: {stats['blocked']}
• 👥 Всего подписчиков: {total_subscribers}
• 📈 Успешность: {round(stats['sent']/total_subscribers*100, 1) if total_subscribers > 0 else 0}%"""


async def broadcast_new_code(bot: Bot, code: CodeModel) -> Dict[str, int]:
    """Рассылка нового кода с сохранением связей сообщений"""
    logger.info(f"🚀 Начинаю рассылку нового кода: {code.code}")
    
    # Получаем подписчиков
    subscribers = await db.get_all_subscribers()
    if not subscribers:
        logger.warning("❌ Нет подписчиков для рассылки")
        return {"sent": 0, "failed": 0, "blocked": 0}
    
    # Подготавливаем сообщение и клавиатуру
    text = MessageTemplates.new_code_message(code)
    keyboard = get_code_activation_keyboard(code.code)
    
    # Выполняем рассылку
    broadcast_manager = BroadcastManager(bot)
    result = await broadcast_manager.broadcast_to_users(
        user_ids=subscribers,
        text=text,
        reply_markup=keyboard
    )
    
    # Сохраняем связи сообщений с кодом для будущих обновлений
    saved_count = 0
    for message_info in result['messages']:
        try:
            # Сохраняем связь кода с сообщением
            await db.save_code_message(code.id, message_info['user_id'], message_info['message_id'])
            saved_count += 1
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения связи сообщения: {e}")
    
    logger.info(f"✅ Рассылка кода {code.code} завершена: {result['stats']}, сохранено связей: {saved_count}")
    return result['stats']


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
        logger.warning("❌ Нет подписчиков для рассылки поста")
        return {"sent": 0, "failed": 0, "blocked": 0}
    
    # Подготавливаем сообщение и клавиатуру
    text = MessageTemplates.custom_post_message(post_data)
    
    if post_data.get('button_text') and post_data.get('button_url'):
        keyboard = get_custom_post_with_button_keyboard(
            post_data['button_text'],
            post_data['button_url']
        )
    else:
        keyboard = get_custom_post_keyboard()
    
    # Выполняем рассылку
    broadcast_manager = BroadcastManager(bot)
    result = await broadcast_manager.broadcast_to_users(
        user_ids=subscribers,
        text=text,
        photo=image_file_id,
        reply_markup=keyboard
    )
    
    # Отправляем отчет админу
    report_text = MessageTemplates.broadcast_report(result['stats'], len(subscribers))
    try:
        await bot.send_message(chat_id=admin_id, text=report_text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки отчета админу: {e}")
    
    logger.info(f"✅ Рассылка поста завершена: {result['stats']}")
    return result['stats']


async def update_expired_code_messages(bot: Bot, code_value: str):
    """КЛЮЧЕВАЯ ФУНКЦИЯ: Обновляет старые сообщения при истечении кода"""
    logger.info(f"🔄 Обновляю сообщения для истекшего кода: {code_value}")
    
    try:
        # ВАЖНО: Получаем все сообщения связанные с этим кодом ПО ЕГО ЗНАЧЕНИЮ
        # Используем специальный метод, который ищет по коду, а не по ID (который уже может быть удален)
        messages = await db.get_code_messages_by_value(code_value)
        
        if not messages:
            logger.warning(f"⚠️ Сообщения для кода {code_value} не найдены")
            return
        
        logger.info(f"📨 Найдено сообщений для обновления: {len(messages)}")
        
        # Подготавливаем новые данные для истекшего кода
        expired_text = MessageTemplates.expired_code_message(code_value)
        expired_keyboard = get_code_activation_keyboard(code_value, is_expired=True)
        
        # Счетчики обработки
        updated_count = 0
        failed_count = 0
        
        # Обновляем сообщения пакетами для оптимизации
        for i, msg in enumerate(messages):
            try:
                await bot.edit_message_text(
                    chat_id=msg.user_id,
                    message_id=msg.message_id,
                    text=expired_text,
                    reply_markup=expired_keyboard,
                    parse_mode="HTML"
                )
                updated_count += 1
                
                # Небольшая пауза каждые 5 сообщений для избежания rate limit
                if (i + 1) % 5 == 0:
                    await asyncio.sleep(0.2)
                
            except (TelegramBadRequest, TelegramForbiddenError) as e:
                # Сообщение удалено пользователем или бот заблокирован
                failed_count += 1
                logger.debug(f"Сообщение {msg.id} недоступно: {e}")
                continue
                
            except TelegramRetryAfter as e:
                # Обрабатываем rate limit
                logger.warning(f"Rate limit при обновлении: ждем {e.retry_after} сек")
                await asyncio.sleep(e.retry_after)
                
                # Повторяем попытку
                try:
                    await bot.edit_message_text(
                        chat_id=msg.user_id,
                        message_id=msg.message_id,
                        text=expired_text,
                        reply_markup=expired_keyboard,
                        parse_mode="HTML"
                    )
                    updated_count += 1
                except:
                    failed_count += 1
                
            except Exception as e:
                failed_count += 1
                logger.error(f"❌ Ошибка обновления сообщения {msg.id}: {e}")
        
        logger.info(f"✅ Обновление сообщений для кода {code_value} завершено:")
        logger.info(f"   📝 Обновлено: {updated_count}")
        logger.info(f"   ❌ Ошибок: {failed_count}")
        
        # Удаляем записи об обновленных сообщениях (они больше не нужны)
        try:
            await db.cleanup_expired_code_messages(code_value)
            logger.info(f"🧹 Очищены записи сообщений для кода {code_value}")
        except Exception as e:
            logger.error(f"❌ Ошибка очистки записей сообщений: {e}")
        
    except Exception as e:
        logger.error(f"💥 Критическая ошибка при обновлении сообщений для кода {code_value}: {e}")


# Дополнительная утилитарная функция для планировщика
async def process_expired_codes(bot: Bot) -> int:
    """Обрабатывает все истекшие коды"""
    try:
        from utils.date_utils import get_moscow_time
        moscow_now = get_moscow_time()
        logger.info(f"🔍 Проверка истекших кодов: {moscow_now.strftime('%d.%m.%Y %H:%M:%S')}")
        
        # Получаем коды к истечению
        codes_to_expire = await db.get_codes_to_expire()
        
        if not codes_to_expire:
            logger.debug("✅ Истекших кодов не найдено")
            return 0
        
        logger.info(f"⏰ Найдено истекших кодов: {len(codes_to_expire)}")
        
        processed_count = 0
        for code in codes_to_expire:
            try:
                logger.info(f"🗑️ Обрабатываю истекший код: {code.code}")
                
                # 1. СНАЧАЛА обновляем сообщения (пока код еще есть в БД)
                await update_expired_code_messages(bot, code.code)
                
                # 2. ПОТОМ удаляем код из БД
                success = await db.expire_code_by_id(code.id)
                
                if success:
                    logger.info(f"✅ Код {code.code} успешно деактивирован")
                    processed_count += 1
                else:
                    logger.warning(f"⚠️ Не удалось деактивировать код {code.code}")
                
                # Небольшая пауза между обработкой кодов
                await asyncio.sleep(2)
                
            except Exception as e:
                logger.error(f"❌ Ошибка обработки кода {code.code}: {e}")
                continue
        
        if processed_count > 0:
            logger.info(f"🎯 Обработано истекших кодов: {processed_count}")
        
        return processed_count
        
    except Exception as e:
        logger.error(f"💥 Критическая ошибка при обработке истекших кодов: {e}")
        return 0
    
"""
Интеграционный файл для исправления системы обновления истекших сообщений
"""

# ========== ФАЙЛ 1: utils/broadcast.py ==========
"""
ПОЛНАЯ РАБОЧАЯ СИСТЕМА РАССЫЛКИ С ОБНОВЛЕНИЕМ ИСТЕКШИХ СООБЩЕНИЙ
"""
import asyncio
import logging
from typing import List, Dict, Any, Optional
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

logger = logging.getLogger(__name__)


class BroadcastManager:
    def __init__(self, bot: Bot, max_concurrent: int = 10, delay: float = 0.05):
        self.bot = bot
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.delay = delay
        self.stats = {"sent": 0, "failed": 0, "blocked": 0}
        self.sent_messages = []
    
    async def send_message_safe(self, user_id: int, text: str = None, photo: str = None, reply_markup=None, parse_mode: str = "HTML") -> Optional[int]:
        async with self.semaphore:
            try:
                if photo:
                    message = await self.bot.send_photo(chat_id=user_id, photo=photo, caption=text, reply_markup=reply_markup, parse_mode=parse_mode)
                else:
                    message = await self.bot.send_message(chat_id=user_id, text=text, reply_markup=reply_markup, parse_mode=parse_mode)
                
                self.stats["sent"] += 1
                self.sent_messages.append({'user_id': user_id, 'message_id': message.message_id})
                await asyncio.sleep(self.delay)
                return message.message_id
            except TelegramForbiddenError:
                self.stats["blocked"] += 1
                return None
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after)
                return await self.send_message_safe(user_id, text, photo, reply_markup, parse_mode)
            except Exception as e:
                self.stats["failed"] += 1
                logger.error(f"Ошибка отправки пользователю {user_id}: {e}")
                return None
    
    async def broadcast_to_users(self, user_ids: List[int], text: str = None, photo: str = None, reply_markup=None) -> Dict[str, Any]:
        self.stats = {"sent": 0, "failed": 0, "blocked": 0}
        self.sent_messages = []
        
        tasks = [self.send_message_safe(user_id, text, photo, reply_markup) for user_id in user_ids]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        return {'stats': self.stats.copy(), 'messages': self.sent_messages.copy()}


async def broadcast_new_code(bot: Bot, code) -> Dict[str, int]:
    """Рассылка нового кода с сохранением связей сообщений"""
    from database import db
    from keyboards.inline import get_code_activation_keyboard
    from utils.date_utils import format_expiry_date
    
    logger.info(f"🚀 Начинаю рассылку нового кода: {code.code}")
    
    subscribers = await db.get_all_subscribers()
    if not subscribers:
        return {"sent": 0, "failed": 0, "blocked": 0}
    
    # Формируем сообщение
    text = f"""🎉 <b>Новый промо-код Genshin Impact!</b>

🔥 <b>Код:</b> <code>{code.code}</code>
💎 <b>Награды:</b> {code.rewards or 'Не указано'}
📝 <b>Описание:</b> {code.description or 'Промо-код Genshin Impact'}"""
    
    if code.expires_date:
        text += f"\n\n⏰ <b>Действует до:</b> {format_expiry_date(code.expires_date)}"
    
    text += "\n\n<i>💡 Нажми кнопку ниже для активации!</i>"
    
    keyboard = get_code_activation_keyboard(code.code)
    
    broadcast_manager = BroadcastManager(bot)
    result = await broadcast_manager.broadcast_to_users(user_ids=subscribers, text=text, reply_markup=keyboard)
    
    # Сохраняем связи сообщений с кодом
    saved_count = 0
    for message_info in result['messages']:
        try:
            await db.save_code_message(code.id, message_info['user_id'], message_info['message_id'])
            saved_count += 1
        except Exception as e:
            logger.error(f"Ошибка сохранения связи сообщения: {e}")
    
    logger.info(f"✅ Рассылка кода {code.code} завершена: {result['stats']}, сохранено связей: {saved_count}")
    return result['stats']


async def broadcast_custom_post(bot: Bot, post_data: Dict[str, Any], image_file_id: Optional[str], admin_id: int) -> Dict[str, int]:
    """Рассылка кастомного поста"""
    from database import db
    from keyboards.inline import get_custom_post_keyboard, get_custom_post_with_button_keyboard
    
    logger.info(f"📢 Начинаю рассылку поста: {post_data['title']}")
    
    subscribers = await db.get_all_subscribers()
    if not subscribers:
        return {"sent": 0, "failed": 0, "blocked": 0}
    
    text = f"{post_data['title']}\n\n{post_data['text']}"
    
    if post_data.get('button_text') and post_data.get('button_url'):
        keyboard = get_custom_post_with_button_keyboard(post_data['button_text'], post_data['button_url'])
    else:
        keyboard = get_custom_post_keyboard()
    
    broadcast_manager = BroadcastManager(bot)
    result = await broadcast_manager.broadcast_to_users(user_ids=subscribers, text=text, photo=image_file_id, reply_markup=keyboard)
    
    # Отчет админу
    report_text = f"""✅ <b>Рассылка завершена!</b>

📊 <b>Статистика:</b>
• 📤 Отправлено: {result['stats']['sent']}
• ❌ Ошибок: {result['stats']['failed']}
• 🚫 Заблокировано: {result['stats']['blocked']}
• 👥 Всего подписчиков: {len(subscribers)}
• 📈 Успешность: {round(result['stats']['sent']/len(subscribers)*100, 1) if len(subscribers) > 0 else 0}%"""
    
    try:
        await bot.send_message(chat_id=admin_id, text=report_text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка отправки отчета админу: {e}")
    
    return result['stats']


async def update_expired_code_messages(bot: Bot, code_value: str):
    """КЛЮЧЕВАЯ ФУНКЦИЯ: Обновляет старые сообщения при истечении кода"""
    from database import db
    from keyboards.inline import get_code_activation_keyboard
    
    logger.info(f"🔄 Обновляю сообщения для истекшего кода: {code_value}")
    
    try:
        messages = await db.get_code_messages_by_value(code_value)
        
        if not messages:
            logger.warning(f"⚠️ Сообщения для кода {code_value} не найдены")
            return
        
        logger.info(f"📨 Найдено сообщений для обновления: {len(messages)}")
        
        expired_text = f"""❌ <b>Промо-код истек</b>

Код <code>{code_value}</code> больше недействителен.

🔔 <i>Подпишись на уведомления, чтобы не пропустить новые коды!</i>"""
        
        expired_keyboard = get_code_activation_keyboard(code_value, is_expired=True)
        
        updated_count = 0
        failed_count = 0
        
        for i, msg in enumerate(messages):
            try:
                await bot.edit_message_text(
                    chat_id=msg.user_id,
                    message_id=msg.message_id,
                    text=expired_text,
                    reply_markup=expired_keyboard,
                    parse_mode="HTML"
                )
                updated_count += 1
                
                if (i + 1) % 5 == 0:
                    await asyncio.sleep(0.2)
                
            except (TelegramBadRequest, TelegramForbiddenError):
                failed_count += 1
                continue
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after)
                try:
                    await bot.edit_message_text(chat_id=msg.user_id, message_id=msg.message_id, text=expired_text, reply_markup=expired_keyboard, parse_mode="HTML")
                    updated_count += 1
                except:
                    failed_count += 1
            except Exception as e:
                failed_count += 1
                logger.error(f"Ошибка обновления сообщения {msg.id}: {e}")
        
        logger.info(f"✅ Обновление сообщений для кода {code_value} завершено: обновлено {updated_count}, ошибок {failed_count}")
        
        try:
            await db.cleanup_expired_code_messages(code_value)
        except Exception as e:
            logger.error(f"Ошибка очистки записей сообщений: {e}")
        
    except Exception as e:
        logger.error(f"💥 Критическая ошибка при обновлении сообщений для кода {code_value}: {e}")