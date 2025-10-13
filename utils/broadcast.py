"""
Исправленная система сохранения и обновления сообщений с кодами
"""
import asyncio
import logging
from typing import List, Dict, Any, Optional
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

from database import db
from models import CodeModel, CodeMessageModel
from keyboards.inline import get_code_activation_keyboard, get_custom_post_keyboard, get_custom_post_with_button_keyboard
from utils.date_utils import format_expiry_date

logger = logging.getLogger(__name__)


class BroadcastManager:
    """Управляет рассылкой сообщений с сохранением связей"""
    
    def __init__(self, bot: Bot, max_concurrent: int = 10, delay: float = 0.05):
        self.bot = bot
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.delay = delay
        self.stats = {"sent": 0, "failed": 0, "blocked": 0}
        self.message_records = []  # Записи о отправленных сообщениях
    
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
                await asyncio.sleep(self.delay)
                return message.message_id  # Возвращаем ID сообщения
                
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
    
    async def broadcast_with_tracking(
        self,
        user_ids: List[int],
        text: str = None,
        photo: str = None,
        reply_markup=None,
        code_id: Optional[int] = None
    ) -> Dict[str, int]:
        """Рассылка с отслеживанием сообщений для будущих обновлений"""
        self.stats = {"sent": 0, "failed": 0, "blocked": 0}
        self.message_records = []
        
        tasks = [
            self._send_and_record(user_id, text, photo, reply_markup, code_id)
            for user_id in user_ids
        ]
        
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Массовое сохранение записей о сообщениях в базе данных
        if self.message_records and code_id:
            try:
                await db.save_message_batch(self.message_records)
                logger.info(f"Сохранено {len(self.message_records)} записей о сообщениях")
            except Exception as e:
                logger.error(f"Ошибка сохранения записей сообщений: {e}")
        
        return self.stats.copy()
    
    async def _send_and_record(self, user_id: int, text: str, photo: str, reply_markup, code_id: Optional[int]):
        """Отправляет сообщение и записывает данные о нем"""
        message_id = await self.send_message_safe(user_id, text, photo, reply_markup)
        
        if message_id and code_id:
            # Сохраняем запись для будущего обновления
            self.message_records.append({
                'code_id': code_id,
                'user_id': user_id,
                'message_id': message_id,
                'is_active': True
            })


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
    logger.info(f"Начинаю рассылку нового кода: {code.code}")
    
    # Получаем подписчиков
    subscribers = await db.get_all_subscribers()
    if not subscribers:
        logger.warning("Нет подписчиков для рассылки")
        return {"sent": 0, "failed": 0, "blocked": 0}
    
    # Подготавливаем сообщение и клавиатуру
    text = MessageTemplates.new_code_message(code)
    keyboard = get_code_activation_keyboard(code.code)
    
    # Выполняем рассылку с отслеживанием
    broadcast_manager = BroadcastManager(bot)
    stats = await broadcast_manager.broadcast_with_tracking(
        user_ids=subscribers,
        text=text,
        reply_markup=keyboard,
        code_id=code.id
    )
    
    logger.info(f"Рассылка кода завершена: {stats}")
    return stats


async def broadcast_custom_post(
    bot: Bot,
    post_data: Dict[str, Any],
    image_file_id: Optional[str],
    admin_id: int
) -> Dict[str, int]:
    """Рассылка кастомного поста"""
    logger.info(f"Начинаю рассылку поста: {post_data['title']}")
    
    # Получаем подписчиков
    subscribers = await db.get_all_subscribers()
    if not subscribers:
        logger.warning("Нет подписчиков для рассылки поста")
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
    
    # Выполняем рассылку БЕЗ отслеживания (для постов не нужно)
    broadcast_manager = BroadcastManager(bot)
    stats = await broadcast_manager.broadcast_with_tracking(
        user_ids=subscribers,
        text=text,
        photo=image_file_id,
        reply_markup=keyboard,
        code_id=None  # Для постов не отслеживаем
    )
    
    # Отправляем отчет админу
    report_text = MessageTemplates.broadcast_report(stats, len(subscribers))
    try:
        await bot.send_message(chat_id=admin_id, text=report_text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка отправки отчета админу: {e}")
    
    logger.info(f"Рассылка поста завершена: {stats}")
    return stats


async def update_expired_code_messages(bot: Bot, code_value: str):
    """Обновляет старые сообщения при истечении кода"""
    logger.info(f"Обновляю сообщения для истекшего кода: {code_value}")
    
    try:
        # Получаем все сообщения связанные с этим кодом
        messages = await db.get_messages_by_code_value(code_value)
        
        if not messages:
            logger.info(f"Сообщения для кода {code_value} не найдены")
            return
        
        # Подготавливаем новые данные
        expired_text = MessageTemplates.expired_code_message(code_value)
        expired_keyboard = get_code_activation_keyboard(code_value, is_expired=True)
        
        # Счетчики для статистики
        updated_count = 0
        failed_count = 0
        
        # Обновляем сообщения порциями
        semaphore = asyncio.Semaphore(5)  # Ограничиваем до 5 одновременных обновлений
        
        async def update_single_message(msg_record):
            async with semaphore:
                try:
                    await bot.edit_message_text(
                        chat_id=msg_record['user_id'],
                        message_id=msg_record['message_id'],
                        text=expired_text,
                        reply_markup=expired_keyboard,
                        parse_mode="HTML"
                    )
                    return True
                except (TelegramBadRequest, TelegramForbiddenError) as e:
                    logger.debug(f"Сообщение {msg_record['message_id']} недоступно: {e}")
                    return False
                except Exception as e:
                    logger.error(f"Ошибка обновления сообщения {msg_record['message_id']}: {e}")
                    return False
        
        # Обновляем все сообщения
        tasks = [update_single_message(msg) for msg in messages]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Подсчитываем статистику
        for result in results:
            if result is True:
                updated_count += 1
            else:
                failed_count += 1
        
        # Помечаем сообщения как неактивные в БД
        await db.deactivate_messages_by_code_value(code_value)
        
        logger.info(f"Обновление сообщений для кода {code_value} завершено: обновлено {updated_count}, ошибок {failed_count}")
        
    except Exception as e:
        logger.error(f"Критическая ошибка при обновлении сообщений: {e}")


# Функция для планировщика
async def update_expired_code_messages_by_id(bot: Bot, code_id: int, code_value: str):
    """Обновляет истекшие сообщения по ID кода (для планировщика)"""
    logger.info(f"Планировщик: обновляю сообщения для кода {code_value} (ID: {code_id})")
    await update_expired_code_messages(bot, code_value)