"""
Полная система рассылки с сохранением ID сообщений и обновлением истекших кодов
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
    """Управляет рассылкой сообщений с сохранением ID"""
    
    def __init__(self, bot: Bot, max_concurrent: int = 10, delay: float = 0.05):
        self.bot = bot
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.delay = delay
        self.stats = {"sent": 0, "failed": 0, "blocked": 0}
        self.sent_messages = []  # Список (user_id, message_id)
    
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
                self.sent_messages.append((user_id, message.message_id))
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
        """Рассылка сообщений списку пользователей с сохранением ID"""
        self.stats = {"sent": 0, "failed": 0, "blocked": 0}
        self.sent_messages = []
        
        tasks = [
            self.send_message_safe(user_id, text, photo, reply_markup)
            for user_id in user_ids
        ]
        
        await asyncio.gather(*tasks, return_exceptions=True)
        return {**self.stats, "sent_messages": self.sent_messages}


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
    def broadcast_report(stats: Dict[str, Any], total_subscribers: int) -> str:
        """Формирует отчет о рассылке"""
        return f"""✅ <b>Рассылка завершена!</b>

📊 <b>Статистика:</b>
• 📤 Отправлено: {stats['sent']}
• ❌ Ошибок: {stats['failed']}
• 🚫 Заблокировано: {stats['blocked']}
• 👥 Всего подписчиков: {total_subscribers}
• 📈 Успешность: {round(stats['sent']/total_subscribers*100, 1) if total_subscribers > 0 else 0}%"""


async def broadcast_new_code(bot: Bot, code: CodeModel) -> Dict[str, Any]:
    """Рассылка нового кода с сохранением связей сообщений"""
    logger.info(f"🚀 Начинаю рассылку нового кода: {code.code}")
    
    # Получаем подписчиков
    subscribers = await db.get_all_subscribers()
    if not subscribers:
        logger.warning("⚠️ Нет подписчиков для рассылки")
        return {"sent": 0, "failed": 0, "blocked": 0}
    
    logger.info(f"📤 Подписчиков для рассылки: {len(subscribers)}")
    
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
    
    # Сохраняем связи сообщений с кодом
    saved_count = 0
    for user_id, message_id in result.get("sent_messages", []):
        try:
            message_model = CodeMessageModel(
                code_id=code.id,
                user_id=user_id,
                message_id=message_id
            )
            success = await db.save_code_message(message_model)
            if success:
                saved_count += 1
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения связи сообщения {user_id}:{message_id}: {e}")
    
    logger.info(f"💾 Сохранено связей сообщений: {saved_count}/{result['sent']}")
    logger.info(f"✅ Рассылка кода завершена: {result}")
    
    return {
        "sent": result["sent"],
        "failed": result["failed"],
        "blocked": result["blocked"],
        "saved_links": saved_count
    }


async def broadcast_custom_post(
    bot: Bot,
    post_data: Dict[str, Any],
    image_file_id: Optional[str],
    admin_id: int
) -> Dict[str, Any]:
    """Рассылка кастомного поста"""
    logger.info(f"📢 Начинаю рассылку поста: {post_data['title']}")
    
    # Получаем подписчиков
    subscribers = await db.get_all_subscribers()
    if not subscribers:
        logger.warning("⚠️ Нет подписчиков для рассылки поста")
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
    report_text = MessageTemplates.broadcast_report(result, len(subscribers))
    try:
        await bot.send_message(chat_id=admin_id, text=report_text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки отчета админу: {e}")
    
    logger.info(f"✅ Рассылка поста завершена: {result}")
    return result


async def update_expired_code_messages(bot: Bot, code_value: str) -> Dict[str, int]:
    """
    Обновляет старые сообщения при истечении кода
    КРИТИЧНО: вызывается ДО удаления кода из БД
    """
    logger.info(f"🔄 Обновляю сообщения для истекшего кода: {code_value}")
    
    try:
        # ВАЖНО: получаем сообщения ДО удаления кода
        messages = await db.get_code_messages_by_value(code_value)
        
        if not messages:
            logger.info(f"ℹ️ Сообщения для кода {code_value} не найдены")
            return {"updated": 0, "failed": 0}
        
        logger.info(f"📨 Найдено сообщений для обновления: {len(messages)}")
        
        # Подготавливаем новые данные
        expired_text = MessageTemplates.expired_code_message(code_value)
        expired_keyboard = get_code_activation_keyboard(code_value, is_expired=True)
        
        # Статистика обновлений
        updated_count = 0
        failed_count = 0
        
        # Обновляем сообщения
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
                
                # Небольшая пауза для избежания флуд-лимитов
                if i % 10 == 0 and i > 0:
                    await asyncio.sleep(0.5)
                else:
                    await asyncio.sleep(0.1)
                
            except TelegramBadRequest as e:
                if "message is not modified" in str(e).lower():
                    logger.debug(f"Сообщение {msg.user_id}:{msg.message_id} уже обновлено")
                    updated_count += 1
                elif "message to edit not found" in str(e).lower():
                    logger.debug(f"Сообщение {msg.user_id}:{msg.message_id} удалено пользователем")
                    failed_count += 1
                else:
                    logger.warning(f"Ошибка редактирования {msg.user_id}:{msg.message_id}: {e}")
                    failed_count += 1
            except TelegramForbiddenError:
                logger.debug(f"Пользователь {msg.user_id} заблокировал бота")
                failed_count += 1
            except TelegramRetryAfter as e:
                logger.warning(f"Флуд-лимит при обновлении: жду {e.retry_after} сек")
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
                except:
                    failed_count += 1
            except Exception as e:
                logger.error(f"❌ Неожиданная ошибка обновления сообщения {msg.id}: {e}")
                failed_count += 1
        
        result = {"updated": updated_count, "failed": failed_count}
        logger.info(f"✅ Обновление сообщений для кода {code_value} завершено: {result}")
        return result
        
    except Exception as e:
        logger.error(f"💥 Критическая ошибка при обновлении сообщений для {code_value}: {e}")
        return {"updated": 0, "failed": 0}


# Дополнительные утилиты для обновления сообщений
async def cleanup_old_code_messages(bot: Bot, code_id: int) -> int:
    """Очистка старых записей сообщений после обновления"""
    try:
        deleted_count = await db.delete_code_messages_by_code_id(code_id)
        logger.info(f"🗑️ Удалено записей сообщений для кода {code_id}: {deleted_count}")
        return deleted_count
    except Exception as e:
        logger.error(f"❌ Ошибка очистки записей сообщений: {e}")
        return 0


async def get_message_stats() -> Dict[str, int]:
    """Получить статистику сообщений в БД"""
    try:
        stats = await db.get_message_stats()
        return stats
    except Exception as e:
        logger.error(f"❌ Ошибка получения статистики сообщений: {e}")
        return {"total_messages": 0, "active_codes": 0}