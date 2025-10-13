"""
Улучшенная система рассылки с обновлением истекших сообщений
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
        """Формирует сообщение об истекшем коде"""
        return f"""⌛ <b>Промо-код истек</b>

Код <code>{code_value}</code> больше недействителен.

🔔 <i>Подпишись на уведомления, чтобы не пропустить новые коды!</i>

💡 <i>Используй /codes чтобы посмотреть актуальные коды</i>"""
    
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
    """Оптимизированная рассылка нового кода с сохранением связей сообщений"""
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
    stats = {"sent": 0, "failed": 0, "blocked": 0}
    
    # Отправляем всем подписчикам и сохраняем связи сообщений
    for user_id in subscribers:
        message_id = await broadcast_manager.send_message_safe(
            user_id=user_id,
            text=text,
            reply_markup=keyboard
        )
        
        # Сохраняем связь сообщения с кодом для возможного обновления
        if message_id:
            try:
                await db.save_code_message(code.id, user_id, message_id)
            except Exception as e:
                logger.error(f"Ошибка сохранения связи сообщения: {e}")
    
    stats.update(broadcast_manager.stats)
    
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
    stats = {"sent": 0, "failed": 0, "blocked": 0}
    
    for user_id in subscribers:
        await broadcast_manager.send_message_safe(
            user_id=user_id,
            text=text,
            photo=image_file_id,
            reply_markup=keyboard
        )
    
    stats.update(broadcast_manager.stats)
    
    # Отправляем отчет админу
    report_text = MessageTemplates.broadcast_report(stats, len(subscribers))
    try:
        await bot.send_message(chat_id=admin_id, text=report_text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка отправки отчета админу: {e}")
    
    logger.info(f"Рассылка поста завершена: {stats}")
    return stats


async def update_expired_code_messages(bot: Bot, code_value: str):
    """
    КЛЮЧЕВАЯ ФУНКЦИЯ: Обновляет все сообщения с истекшим кодом
    
    1. Получает все сообщения связанные с кодом
    2. Обновляет текст на "код истек"
    3. Меняет клавиатуру на неактивную
    """
    logger.info(f"🔄 Обновляю сообщения для истекшего кода: {code_value}")
    
    try:
        # Получаем все сообщения связанные с этим кодом
        messages = await db.get_code_messages_by_value(code_value)
        
        if not messages:
            logger.info(f"Сообщения для кода {code_value} не найдены")
            return
        
        logger.info(f"Найдено {len(messages)} сообщений для обновления")
        
        # Подготавливаем новые данные
        expired_text = MessageTemplates.expired_code_message(code_value)
        expired_keyboard = get_code_activation_keyboard(code_value, is_expired=True)
        
        updated_count = 0
        error_count = 0
        
        # Обновляем каждое сообщение
        for msg in messages:
            try:
                await bot.edit_message_text(
                    chat_id=msg.user_id,
                    message_id=msg.message_id,
                    text=expired_text,
                    reply_markup=expired_keyboard,
                    parse_mode="HTML"
                )
                updated_count += 1
                
                # Небольшая пауза между обновлениями
                await asyncio.sleep(0.1)
                
            except TelegramBadRequest as e:
                error_count += 1
                # Сообщение может быть удалено пользователем или невозможно отредактировать
                if "message to edit not found" in str(e).lower():
                    logger.debug(f"Сообщение {msg.message_id} у пользователя {msg.user_id} удалено")
                elif "message is not modified" in str(e).lower():
                    logger.debug(f"Сообщение {msg.message_id} уже обновлено")
                else:
                    logger.warning(f"Ошибка обновления сообщения {msg.message_id}: {e}")
                    
            except TelegramForbiddenError:
                error_count += 1
                logger.debug(f"Пользователь {msg.user_id} заблокировал бота")
                
            except Exception as e:
                error_count += 1
                logger.error(f"Неожиданная ошибка обновления сообщения {msg.message_id}: {e}")
        
        logger.info(f"✅ Обновление завершено для кода {code_value}: обновлено {updated_count}, ошибок {error_count}")
        
        # Помечаем сообщения как неактивные в БД
        try:
            await db.deactivate_code_messages(code_value)
        except Exception as e:
            logger.error(f"Ошибка деактивации сообщений в БД: {e}")
        
    except Exception as e:
        logger.error(f"💥 Критическая ошибка при обновлении сообщений для кода {code_value}: {e}")