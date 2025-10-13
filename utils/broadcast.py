"""
Оптимизированная система рассылки сообщений с батчевой обработкой
"""
import asyncio
import logging
from typing import List, Dict, Any, Optional
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

from database import db
from models import CodeModel
from keyboards.inline import get_code_activation_keyboard, get_custom_post_keyboard, get_custom_post_with_button_keyboard
from utils.date_utils import format_expiry_date

logger = logging.getLogger(__name__)


class BroadcastManager:
    """Управляет рассылкой сообщений с оптимизацией"""
    
    def __init__(self, bot: Bot, max_concurrent: int = 10, delay: float = 0.05):
        self.bot = bot
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.delay = delay
        self.stats = {"sent": 0, "failed": 0, "blocked": 0}
    
    async def send_message_safe(
        self,
        user_id: int,
        text: str = None,
        photo: str = None,
        reply_markup=None,
        parse_mode: str = "HTML"
    ) -> bool:
        """Безопасная отправка сообщения одному пользователю"""
        async with self.semaphore:
            try:
                if photo:
                    await self.bot.send_photo(
                        chat_id=user_id,
                        photo=photo,
                        caption=text,
                        reply_markup=reply_markup,
                        parse_mode=parse_mode
                    )
                else:
                    await self.bot.send_message(
                        chat_id=user_id,
                        text=text,
                        reply_markup=reply_markup,
                        parse_mode=parse_mode
                    )
                
                self.stats["sent"] += 1
                await asyncio.sleep(self.delay)
                return True
                
            except TelegramForbiddenError:
                self.stats["blocked"] += 1
                logger.debug(f"Пользователь {user_id} заблокировал бота")
                return False
                
            except TelegramRetryAfter as e:
                logger.warning(f"Флуд-лимит: ждем {e.retry_after} секунд")
                await asyncio.sleep(e.retry_after)
                return await self.send_message_safe(user_id, text, photo, reply_markup, parse_mode)
                
            except Exception as e:
                self.stats["failed"] += 1
                logger.error(f"Ошибка отправки пользователю {user_id}: {e}")
                return False
    
    async def broadcast_to_users(
        self,
        user_ids: List[int],
        text: str = None,
        photo: str = None,
        reply_markup=None
    ) -> Dict[str, int]:
        """Рассылка сообщений списку пользователей"""
        self.stats = {"sent": 0, "failed": 0, "blocked": 0}
        
        tasks = [
            self.send_message_safe(user_id, text, photo, reply_markup)
            for user_id in user_ids
        ]
        
        await asyncio.gather(*tasks, return_exceptions=True)
        return self.stats.copy()


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
• 📈 Успешность: {round(stats['sent']/total_subscribers*100, 1)}%"""


async def broadcast_new_code(bot: Bot, code: CodeModel) -> Dict[str, int]:
    """Оптимизированная рассылка нового кода"""
    logger.info(f"Начинаю рассылку нового кода: {code.code}")
    
    # Получаем подписчиков
    subscribers = await db.get_all_subscribers()
    if not subscribers:
        logger.warning("Нет подписчиков для рассылки")
        return {"sent": 0, "failed": 0, "blocked": 0}
    
    # Подготавливаем сообщение и клавиатуру
    text = MessageTemplates.new_code_message(code)
    keyboard = get_code_activation_keyboard(code.code)
    
    # Выполняем рассылку
    broadcast_manager = BroadcastManager(bot)
    stats = await broadcast_manager.broadcast_to_users(
        user_ids=subscribers,
        text=text,
        reply_markup=keyboard
    )
    
    # Сохраняем связи сообщений с кодом (упрощенная версия)
    # В реальной реализации нужно сохранять message_id каждого отправленного сообщения
    
    logger.info(f"Рассылка кода завершена: {stats}")
    return stats


async def broadcast_custom_post(
    bot: Bot,
    post_data: Dict[str, Any],
    image_file_id: Optional[str],
    admin_id: int
) -> Dict[str, int]:
    """Оптимизированная рассылка кастомного поста"""
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
    
    # Выполняем рассылку
    broadcast_manager = BroadcastManager(bot)
    stats = await broadcast_manager.broadcast_to_users(
        user_ids=subscribers,
        text=text,
        photo=image_file_id,
        reply_markup=keyboard
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
        # Поскольку код уже удален из БД, используем обходной путь
        messages = await db.get_code_messages_by_value(code_value)
        
        if not messages:
            logger.info(f"Сообщения для кода {code_value} не найдены")
            return
        
        # Подготавливаем новые данные
        expired_text = f"""❌ <b>Промо-код истек</b>

Код <code>{code_value}</code> больше недействителен.

🔔 <i>Подпишись на уведомления, чтобы не пропустить новые коды!</i>"""
        
        expired_keyboard = get_code_activation_keyboard(code_value, is_expired=True)
        
        # Создаем менеджер для безопасного обновления
        update_manager = BroadcastManager(bot, max_concurrent=5)
        
        # Обновляем сообщения
        for msg in messages:
            try:
                await bot.edit_message_text(
                    chat_id=msg.user_id,
                    message_id=msg.message_id,
                    text=expired_text,
                    reply_markup=expired_keyboard,
                    parse_mode="HTML"
                )
                await asyncio.sleep(0.1)  # Более медленная обработка для edit операций
                
            except (TelegramBadRequest, TelegramForbiddenError):
                # Сообщение удалено пользователем или бот заблокирован
                continue
            except Exception as e:
                logger.error(f"Ошибка обновления сообщения {msg.id}: {e}")
        
        logger.info(f"Обновление сообщений для кода {code_value} завершено")
        
    except Exception as e:
        logger.error(f"Критическая ошибка при обновлении сообщений: {e}")