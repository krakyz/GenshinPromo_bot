import asyncio
import logging
from aiogram import Bot
from database import db
from utils.date_utils import get_moscow_time

logger = logging.getLogger(__name__)

async def check_expired_codes(bot: Bot):
    """Проверка и обновление истекших кодов по московскому времени"""
    try:
        moscow_now = get_moscow_time()
        logger.info(f"Проверка истекших кодов. Московское время: {moscow_now.strftime('%d.%m.%Y %H:%M:%S МСК')}")
        
        codes_to_expire = await db.get_codes_to_expire()
        
        if codes_to_expire:
            logger.info(f"Найдено кодов к истечению: {len(codes_to_expire)}")
        
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
