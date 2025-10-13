import asyncio
import logging
from aiogram import Bot
from database import db

logger = logging.getLogger(__name__)

async def check_expired_codes(bot: Bot):
    """Проверка и обновление истекших кодов"""
    try:
        codes_to_expire = await db.get_codes_to_expire()
        
        for code in codes_to_expire:
            logger.info(f"Автоматически истекает код: {code.code}")
            
            # Помечаем код как истекший
            success = await db.expire_code_by_id(code.id)
            
            if success:
                # Обновляем все старые сообщения с этим кодом
                from handlers.admin import update_expired_code_messages
                await update_expired_code_messages(bot, code.code)
                logger.info(f"Код {code.code} истек, сообщения обновлены")
            
            await asyncio.sleep(1)
    
    except Exception as e:
        logger.error(f"Ошибка при проверке истекших кодов: {e}")

async def start_scheduler(bot: Bot):
    """Запуск планировщика проверки истекших кодов"""
    logger.info("Планировщик истечения кодов запущен")
    
    while True:
        try:
            await check_expired_codes(bot)
            await asyncio.sleep(300)  # Проверка каждые 5 минут
        except Exception as e:
            logger.error(f"Ошибка планировщика: {e}")
            await asyncio.sleep(60)  # При ошибке - пауза 1 минута