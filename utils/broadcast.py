"""
Полная система рассылки с сохранением и обновлением сообщений
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
    """Управляет рассылкой сообщений с оптимизацией и сохранением ID"""
    
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
        """Безопасная отправка сообщения с возвратом message_id"""
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
        success_rate = round(stats['sent']/total_subscribers*100, 1) if total_subscribers > 0 else 0
        return f"""✅ <b>Рассылка завершена!</b>

📊 <b>Статистика:</b>
• 📤 Отправлено: {stats['sent']}
• ❌ Ошибок: {stats['failed']}
• 🚫 Заблокировано: {stats['blocked']}
• 👥 Всего подписчиков: {total_subscribers}
• 📈 Успешность: {success_rate}%"""


async def broadcast_new_code(bot: Bot, code: CodeModel) -> Dict[str, int]:
    """Рассылка нового кода с сохранением связей сообщений"""
    logger.info(f"Начинаю рассылку нового кода: {code.code}")
    
    try:
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
        
        sent_messages = []  # Список успешно отправленных сообщений
        
        for user_id in subscribers:
            message_id = await broadcast_manager.send_message_safe(
                user_id=user_id,
                text=text,
                reply_markup=keyboard
            )
            
            # Если сообщение отправлено успешно, сохраняем связь
            if message_id:
                sent_messages.append((user_id, message_id))
        
        # Сохраняем связи сообщений с кодом в базу данных
        if sent_messages and code.id:
            await db.save_code_messages(code.id, sent_messages)
            logger.info(f"Сохранено {len(sent_messages)} связей сообщений для кода {code.code}")
        
        logger.info(f"Рассылка кода завершена: {broadcast_manager.stats}")
        return broadcast_manager.stats
        
    except Exception as e:
        logger.error(f"Критическая ошибка рассылки кода {code.code}: {e}")
        return {"sent": 0, "failed": 0, "blocked": 0}


async def broadcast_custom_post(
    bot: Bot,
    post_data: Dict[str, Any],
    image_file_id: Optional[str],
    admin_id: int
) -> Dict[str, int]:
    """Рассылка кастомного поста"""
    logger.info(f"Начинаю рассылку поста: {post_data['title']}")
    
    try:
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
        
        for user_id in subscribers:
            await broadcast_manager.send_message_safe(
                user_id=user_id,
                text=text,
                photo=image_file_id,
                reply_markup=keyboard
            )
        
        # Отправляем отчет админу
        report_text = MessageTemplates.broadcast_report(broadcast_manager.stats, len(subscribers))
        try:
            await bot.send_message(chat_id=admin_id, text=report_text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Ошибка отправки отчета админу: {e}")
        
        logger.info(f"Рассылка поста завершена: {broadcast_manager.stats}")
        return broadcast_manager.stats
        
    except Exception as e:
        logger.error(f"Критическая ошибка рассылки поста: {e}")
        return {"sent": 0, "failed": 0, "blocked": 0}


async def update_expired_code_messages(bot: Bot, code: str):
    """Обновляет сообщения при истечении/деактивации кода"""
    logger.info(f"Начинаю обновление сообщений для истекшего кода: {code}")
    
    try:
        # Получаем все сообщения связанные с этим кодом
        messages = await db.get_code_messages_by_code_value(code)
        
        if not messages:
            logger.warning(f"Сообщения для кода {code} не найдены в базе данных")
            return
        
        logger.info(f"Найдено {len(messages)} сообщений для обновления")
        
        # Подготавливаем новые данные
        expired_text = MessageTemplates.expired_code_message(code)
        expired_keyboard = get_code_activation_keyboard(code, is_expired=True)
        
        # Счетчики для статистики
        updated_count = 0
        failed_count = 0
        deleted_count = 0
        
        # Обновляем сообщения партиями
        for message_record in messages:
            try:
                await bot.edit_message_text(
                    chat_id=message_record['user_id'],
                    message_id=message_record['message_id'],
                    text=expired_text,
                    reply_markup=expired_keyboard,
                    parse_mode="HTML"
                )
                updated_count += 1
                
                # Небольшая пауза между обновлениями
                await asyncio.sleep(0.1)
                
            except TelegramBadRequest as e:
                if "message to edit not found" in str(e).lower() or "message can't be edited" in str(e).lower():
                    # Сообщение удалено пользователем
                    deleted_count += 1
                    logger.debug(f"Сообщение {message_record['message_id']} удалено пользователем {message_record['user_id']}")
                else:
                    failed_count += 1
                    logger.warning(f"Не удалось обновить сообщение {message_record['message_id']}: {e}")
                    
            except TelegramForbiddenError:
                # Бот заблокирован пользователем
                failed_count += 1
                logger.debug(f"Бот заблокирован пользователем {message_record['user_id']}")
                
            except TelegramRetryAfter as e:
                # Флуд-лимит, ждем и повторяем
                logger.warning(f"Флуд-лимит при обновлении: ждем {e.retry_after} секунд")
                await asyncio.sleep(e.retry_after)
                try:
                    await bot.edit_message_text(
                        chat_id=message_record['user_id'],
                        message_id=message_record['message_id'],
                        text=expired_text,
                        reply_markup=expired_keyboard,
                        parse_mode="HTML"
                    )
                    updated_count += 1
                except:
                    failed_count += 1
                    
            except Exception as e:
                failed_count += 1
                logger.error(f"Неожиданная ошибка при обновлении сообщения {message_record['message_id']}: {e}")
        
        # Удаляем записи о сообщениях из базы данных (они больше не актуальны)
        try:
            await db.delete_code_messages_by_code_value(code)
            logger.info(f"Удалены записи сообщений для кода {code}")
        except Exception as e:
            logger.error(f"Ошибка удаления записей сообщений: {e}")
        
        logger.info(f"Обновление сообщений для кода {code} завершено: "
                   f"обновлено {updated_count}, ошибок {failed_count}, удалено пользователями {deleted_count}")
        
    except Exception as e:
        logger.error(f"Критическая ошибка при обновлении сообщений для кода {code}: {e}")


# Утилитарная функция для тестирования
async def test_message_update_system(bot: Bot):
    """Тестирование системы обновления сообщений (для отладки)"""
    logger.info("🔧 Запуск теста системы обновления сообщений")
    
    try:
        # Получаем все активные коды
        codes = await db.get_active_codes()
        
        for code in codes:
            # Получаем сообщения для каждого кода
            messages = await db.get_code_messages_by_code_value(code.code)
            logger.info(f"Код {code.code}: найдено {len(messages) if messages else 0} связанных сообщений")
            
    except Exception as e:
        logger.error(f"Ошибка теста: {e}")


# Дополнительная функция для принудительного обновления всех старых сообщений
async def force_update_all_expired_codes(bot: Bot):
    """Принудительно обновляет все сообщения с истекшими кодами"""
    logger.info("🔧 Принудительное обновление всех истекших кодов")
    
    try:
        # Получаем все истекшие коды из истории
        expired_codes = await db.get_expired_codes_with_messages()
        
        for code_value in expired_codes:
            logger.info(f"Обновляю сообщения для истекшего кода: {code_value}")
            await update_expired_code_messages(bot, code_value)
            await asyncio.sleep(1)  # Пауза между кодами
            
    except Exception as e:
        logger.error(f"Ошибка принудительного обновления: {e}")