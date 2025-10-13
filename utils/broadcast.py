"""
Исправленная система рассылки с сохранением связей сообщений и их обновлением
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


class MessageTemplates:
    """Шаблоны сообщений для рассылки"""
    
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
    """
    ИСПРАВЛЕННАЯ рассылка нового кода с сохранением связей сообщений
    """
    logger.info(f"Начинаю рассылку нового кода: {code.code}")
    
    # Получаем подписчиков
    subscribers = await db.get_all_subscribers()
    if not subscribers:
        logger.warning("Нет подписчиков для рассылки")
        return {"sent": 0, "failed": 0, "blocked": 0}
    
    # Подготавливаем сообщение и клавиатуру
    text = MessageTemplates.new_code_message(code)
    keyboard = get_code_activation_keyboard(code.code)
    
    # Статистика рассылки
    stats = {"sent": 0, "failed": 0, "blocked": 0}
    
    # Рассылаем сообщения с сохранением связей
    for user_id in subscribers:
        try:
            message = await bot.send_message(
                chat_id=user_id,
                text=text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            
            # КРИТИЧНО: Сохраняем связь сообщения с кодом
            await db.save_code_message(
                code_id=code.id,
                user_id=user_id,
                message_id=message.message_id
            )
            
            stats["sent"] += 1
            await asyncio.sleep(0.05)  # Защита от флуд-лимита
            
        except TelegramForbiddenError:
            stats["blocked"] += 1
            logger.debug(f"Пользователь {user_id} заблокировал бота")
            
        except TelegramRetryAfter as e:
            logger.warning(f"Флуд-лимит: ждем {e.retry_after} секунд")
            await asyncio.sleep(e.retry_after)
            # Повторяем попытку
            try:
                message = await bot.send_message(
                    chat_id=user_id,
                    text=text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
                await db.save_code_message(
                    code_id=code.id,
                    user_id=user_id,
                    message_id=message.message_id
                )
                stats["sent"] += 1
            except:
                stats["failed"] += 1
                
        except Exception as e:
            stats["failed"] += 1
            logger.error(f"Ошибка отправки пользователю {user_id}: {e}")
    
    logger.info(f"Рассылка кода завершена: {stats}")
    return stats


async def broadcast_custom_post(bot: Bot, post_data: Dict[str, Any], image_file_id: Optional[str], admin_id: int) -> Dict[str, int]:
    """
    Рассылка кастомного поста
    """
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
    
    # Статистика рассылки
    stats = {"sent": 0, "failed": 0, "blocked": 0}
    
    # Рассылаем сообщения
    for user_id in subscribers:
        try:
            if image_file_id:
                await bot.send_photo(
                    chat_id=user_id,
                    photo=image_file_id,
                    caption=text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
            else:
                await bot.send_message(
                    chat_id=user_id,
                    text=text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
            
            stats["sent"] += 1
            await asyncio.sleep(0.05)
            
        except TelegramForbiddenError:
            stats["blocked"] += 1
            logger.debug(f"Пользователь {user_id} заблокировал бота")
            
        except TelegramRetryAfter as e:
            logger.warning(f"Флуд-лимит: ждем {e.retry_after} секунд")
            await asyncio.sleep(e.retry_after)
            # Повторяем попытку
            try:
                if image_file_id:
                    await bot.send_photo(
                        chat_id=user_id,
                        photo=image_file_id,
                        caption=text,
                        reply_markup=keyboard,
                        parse_mode="HTML"
                    )
                else:
                    await bot.send_message(
                        chat_id=user_id,
                        text=text,
                        reply_markup=keyboard,
                        parse_mode="HTML"
                    )
                stats["sent"] += 1
            except:
                stats["failed"] += 1
                
        except Exception as e:
            stats["failed"] += 1
            logger.error(f"Ошибка отправки пользователю {user_id}: {e}")
    
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
    ИСПРАВЛЕННАЯ функция обновления сообщений при истечении кода
    """
    logger.info(f"Обновляю сообщения для истекшего кода: {code_value}")
    
    try:
        # КРИТИЧНО: Получаем все сообщения связанные с этим кодом ПЕРЕД его удалением
        messages = await db.get_code_messages_by_value(code_value)
        
        if not messages:
            logger.info(f"Сообщения для кода {code_value} не найдены")
            return
        
        logger.info(f"Найдено {len(messages)} сообщений для обновления")
        
        # Подготавливаем новые данные
        expired_text = MessageTemplates.expired_code_message(code_value)
        expired_keyboard = get_code_activation_keyboard(code_value, is_expired=True)
        
        # Обновляем сообщения
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
                await asyncio.sleep(0.05)  # Небольшая пауза между обновлениями
                
            except (TelegramBadRequest, TelegramForbiddenError) as e:
                # Сообщение удалено пользователем или бот заблокирован
                failed_count += 1
                logger.debug(f"Не удалось обновить сообщение {msg.id}: {e}")
                continue
                
            except Exception as e:
                logger.error(f"Ошибка обновления сообщения {msg.id}: {e}")
                failed_count += 1
        
        logger.info(f"Обновление сообщений для кода {code_value} завершено: обновлено {updated_count}, ошибок {failed_count}")
        
        # Удаляем записи о сообщениях (опционально, можно оставить для истории)
        # await db.delete_code_messages_by_value(code_value)
        
    except Exception as e:
        logger.error(f"Критическая ошибка при обновлении сообщений: {e}")
        raise  # Пробрасываем ошибку выше для обработки