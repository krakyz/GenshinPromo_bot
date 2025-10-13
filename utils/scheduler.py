import asyncio
import logging
from aiogram import Bot
from database import db
from utils.date_utils import get_moscow_time

logger = logging.getLogger(__name__)

async def check_expired_codes(bot: Bot):
    """ИСПРАВЛЕНА: Проверка и обновление истекших кодов с обновлением сообщений"""
    try:
        moscow_now = get_moscow_time()
        logger.info(f"Проверка истекших кодов. Московское время: {moscow_now.strftime('%d.%m.%Y %H:%M:%S МСК')}")
        
        codes_to_expire = await db.get_codes_to_expire()
        
        if codes_to_expire:
            logger.info(f"Найдено кодов к истечению: {len(codes_to_expire)}")
        
        for code in codes_to_expire:
            logger.info(f"Автоматически истекает код: {code.code}")
            
            # ИСПРАВЛЕНО: Получаем список сообщений для обновления
            success, messages_to_update = await db.expire_code_by_id(code.id)
            
            if success:
                logger.info(f"Код {code.code} истек, найдено {len(messages_to_update)} сообщений для обновления")
                
                # Обновляем все старые сообщения с этим кодом
                await update_expired_code_messages(bot, code.code, messages_to_update)
                
                logger.info(f"Код {code.code} истек, сообщения обновлены")
            
            await asyncio.sleep(1)
    
    except Exception as e:
        logger.error(f"Ошибка при проверке истекших кодов: {e}")

async def update_expired_code_messages(bot: Bot, code: str, messages_to_update):
    """Обновление старых сообщений при автоматическом истечении кода"""
    logger.info(f"Обновляю {len(messages_to_update)} сообщений для автоматически истекшего кода: {code}")
    
    if not messages_to_update:
        logger.info("Нет сообщений для обновления")
        return
    
    # Формируем текст для автоматически истекшего кода  
    expired_text = f"""
⏰ <b>Промо-код истек</b>

❌ <b>Код:</b> <code>{code}</code>

<i>Срок действия этого промо-кода закончился. Следи за новыми кодами!</i>
"""
    
    # Импортируем функцию из admin
    from keyboards.inline import get_code_activation_keyboard
    keyboard = get_code_activation_keyboard(code, is_expired=True)
    
    updated_count = 0
    failed_count = 0
    
    for message_info in messages_to_update:
        try:
            await bot.edit_message_text(
                chat_id=message_info.user_id,
                message_id=message_info.message_id,
                text=expired_text,
                parse_mode="HTML",
                reply_markup=keyboard
            )
            updated_count += 1
            
            # Небольшая пауза между обновлениями
            await asyncio.sleep(0.05)
            
        except Exception as e:
            # Обрабатываем различные ошибки Telegram
            from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
            
            if isinstance(e, TelegramBadRequest):
                if "message is not modified" in str(e):
                    updated_count += 1  # Сообщение уже обновлено
                elif "message to edit not found" in str(e):
                    logger.debug(f"Сообщение {message_info.message_id} пользователя {message_info.user_id} удалено")
                else:
                    failed_count += 1
                    logger.error(f"Ошибка обновления сообщения {message_info.message_id}: {e}")
            elif isinstance(e, TelegramForbiddenError):
                logger.debug(f"Пользователь {message_info.user_id} заблокировал бота")
            elif isinstance(e, TelegramRetryAfter):
                logger.warning(f"Флуд-лимит при автообновлении: ждем {e.retry_after} секунд")
                await asyncio.sleep(e.retry_after)
                
                # Повторяем попытку
                try:
                    await bot.edit_message_text(
                        chat_id=message_info.user_id,
                        message_id=message_info.message_id,
                        text=expired_text,
                        parse_mode="HTML",
                        reply_markup=keyboard
                    )
                    updated_count += 1
                except Exception:
                    failed_count += 1
            else:
                failed_count += 1
                logger.error(f"Неожиданная ошибка при автообновлении сообщения: {e}")
    
    logger.info(f"Автообновление сообщений завершено. Обновлено: {updated_count}, Ошибок: {failed_count}")

async def start_scheduler(bot: Bot):
    """Запуск планировщика проверки истекших кодов (по московскому времени)"""
    moscow_time = get_moscow_time()
    logger.info(f"Планировщик истечения кодов запущен. Время: {moscow_time.strftime('%d.%m.%Y %H:%M:%S МСК')}")
    
    while True:
        try:
            await check_expired_codes(bot)
            await asyncio.sleep(300)  # Проверка каждые 5 минут
        except Exception as e:
            logger.error(f"Ошибка планировщика: {e}")
            await asyncio.sleep(60)  # При ошибке - пауза 1 минута