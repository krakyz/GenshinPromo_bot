"""
Исправленный utils/broadcast.py с функциями обновления истекших сообщений
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
        """Формирует сообщение для истекшего кода"""
        return f"""❌ <b>Промо-код истек</b>

Код <code>{code_value}</code> больше недействителен.

🔔 <i>Подпишись на уведомления, чтобы не пропустить новые коды!</i>"""
    
    @staticmethod
    def custom_post_message(post_data: Dict[str, Any]) -> str:
        """Формирует кастомное сообщение"""
        return f"{post_data['title']}\n\n{post_data['text']}"


async def broadcast_new_code(bot: Bot, code: CodeModel) -> Dict[str, int]:
    """Рассылка нового кода с сохранением ID сообщений для будущих обновлений"""
    logger.info(f"🚀 Начинаю рассылку нового кода: {code.code}")
    
    # Получаем подписчиков
    subscribers = await db.get_all_subscribers()
    if not subscribers:
        logger.warning("Нет подписчиков для рассылки")
        return {"sent": 0, "failed": 0, "blocked": 0}
    
    # Подготавливаем сообщение и клавиатуру
    text = MessageTemplates.new_code_message(code)
    keyboard = get_code_activation_keyboard(code.code)
    
    # Выполняем рассылку
    broadcast_manager = BroadcastManager(bot, max_concurrent=8, delay=0.1)
    
    # Отправляем сообщения и сохраняем связи
    sent_count = 0
    for user_id in subscribers:
        message_id = await broadcast_manager.send_message_safe(
            user_id=user_id,
            text=text,
            reply_markup=keyboard
        )
        
        # Если сообщение отправлено успешно, сохраняем связь
        if message_id:
            try:
                await db.save_code_message(
                    code_id=code.id, 
                    user_id=user_id, 
                    message_id=message_id,
                    code_value=code.code
                )
                sent_count += 1
            except Exception as e:
                logger.error(f"Ошибка сохранения связи сообщения для {user_id}: {e}")
    
    stats = broadcast_manager.stats
    logger.info(f"✅ Рассылка кода {code.code} завершена. Отправлено: {sent_count}, связей сохранено: {sent_count}")
    
    return stats


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
    broadcast_manager = BroadcastManager(bot, max_concurrent=5, delay=0.2)
    
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


async def update_expired_code_messages(bot: Bot, code_value: str):
    """КЛЮЧЕВАЯ ФУНКЦИЯ: Обновляет старые сообщения при истечении кода"""
    logger.info(f"🔄 Обновляю сообщения для истекшего кода: {code_value}")
    
    try:
        # Получаем все сообщения связанные с этим кодом ПО ЗНАЧЕНИЮ
        messages = await db.get_code_messages_by_value(code_value)
        
        if not messages:
            logger.info(f"Сообщения для кода {code_value} не найдены")
            return
        
        logger.info(f"Найдено {len(messages)} сообщений для обновления")
        
        # Подготавливаем новые данные для истекшего кода
        expired_text = MessageTemplates.expired_code_message(code_value)
        expired_keyboard = get_code_activation_keyboard(code_value, is_expired=True)
        
        # Создаем менеджер для безопасного обновления (медленнее, чем обычная рассылка)
        updated_count = 0
        failed_count = 0
        
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
                logger.debug(f"✅ Обновлено сообщение у пользователя {msg.user_id}")
                
                # Более медленная обработка для edit операций (избегаем лимитов)
                await asyncio.sleep(0.2)
                
            except (TelegramBadRequest, TelegramForbiddenError) as e:
                # Сообщение удалено пользователем или бот заблокирован
                failed_count += 1
                logger.debug(f"❌ Не удалось обновить сообщение у {msg.user_id}: {str(e)[:50]}")
                continue
                
            except TelegramRetryAfter as e:
                logger.warning(f"⏳ Флуд-лимит: ждем {e.retry_after} секунд")
                await asyncio.sleep(e.retry_after)
                
                # Повторная попытка после ожидания
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
        
        logger.info(f"🎯 Обновление сообщений для кода {code_value} завершено:")
        logger.info(f"   ✅ Обновлено: {updated_count}")
        logger.info(f"   ❌ Ошибок: {failed_count}")
        
    except Exception as e:
        logger.error(f"💥 Критическая ошибка при обновлении сообщений для кода {code_value}: {e}")


# Дополнительные утилитарные функции

async def get_broadcast_stats() -> Dict[str, Any]:
    """Получение статистики по рассылкам"""
    try:
        total_users, subscribers_count, _ = await db.get_user_stats()
        active_codes = await db.get_active_codes()
        
        return {
            'total_users': total_users,
            'subscribers_count': subscribers_count,
            'active_codes_count': len(active_codes),
            'unsubscribed_count': total_users - subscribers_count
        }
    except Exception as e:
        logger.error(f"Ошибка получения статистики рассылки: {e}")
        return {
            'total_users': 0,
            'subscribers_count': 0,
            'active_codes_count': 0,
            'unsubscribed_count': 0
        }


async def cleanup_old_code_messages(days_old: int = 30):
    """Очистка старых записей сообщений (для оптимизации БД)"""
    try:
        from datetime import timedelta
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)
        
        async with aiosqlite.connect(db.db_path) as database:
            cursor = await database.execute(
                "DELETE FROM code_messages WHERE created_at < ?", 
                (cutoff_date.isoformat(),)
            )
            await database.commit()
            
            deleted_count = cursor.rowcount
            logger.info(f"🧹 Очищено старых записей сообщений: {deleted_count}")
            return deleted_count
            
    except Exception as e:
        logger.error(f"Ошибка очистки старых сообщений: {e}")
        return 0