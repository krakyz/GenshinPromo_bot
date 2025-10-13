"""
Планировщик с полной обработкой истекших кодов и обновлением сообщений
"""
import asyncio
import logging
from aiogram import Bot

from database import db
from utils.date_utils import get_moscow_time

logger = logging.getLogger(__name__)


async def check_expired_codes(bot: Bot):
    """Проверка и обработка истекших кодов с обновлением сообщений"""
    try:
        moscow_now = get_moscow_time()
        logger.info(f"🔍 Проверка истекших кодов: {moscow_now.strftime('%d.%m.%Y %H:%M:%S')}")
        
        # Получаем коды к истечению
        codes_to_expire = await db.get_codes_to_expire()
        
        if not codes_to_expire:
            logger.debug("✅ Истекших кодов не найдено")
            return
        
        logger.info(f"⏰ Найдено истекших кодов: {len(codes_to_expire)}")
        
        # Импортируем функцию обновления сообщений
        from utils.broadcast import update_expired_code_messages
        
        for code in codes_to_expire:
            try:
                logger.info(f"🗑️ Обрабатываю истекший код: {code.code}")
                
                # 1. СНАЧАЛА обновляем все сообщения с этим кодом
                await update_expired_code_messages(bot, code.code)
                
                # 2. ПОТОМ удаляем код из базы данных
                success = await db.expire_code_by_id(code.id)
                
                if success:
                    logger.info(f"✅ Код {code.code} успешно деактивирован")
                else:
                    logger.warning(f"⚠️ Не удалось деактивировать код {code.code}")
                
                # Пауза между обработкой кодов
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"❌ Ошибка обработки кода {code.code}: {e}")
                
    except Exception as e:
        logger.error(f"💥 Критическая ошибка при проверке истекших кодов: {e}")


async def start_scheduler(bot: Bot):
    """Запуск планировщика задач"""
    moscow_time = get_moscow_time()
    logger.info(f"🚀 Планировщик запущен: {moscow_time.strftime('%d.%m.%Y %H:%M:%S')}")
    
    while True:
        try:
            # Проверяем истекшие коды каждые 5 минут
            await check_expired_codes(bot)
            await asyncio.sleep(300)  # 5 минут
            
        except Exception as e:
            logger.error(f"💥 Ошибка в планировщике: {e}")
            await asyncio.sleep(60)  # При ошибке ждем 1 минуту


# Функция для ручного запуска (для тестирования)
async def manual_check_expired_codes(bot: Bot):
    """Ручная проверка истекших кодов для отладки"""
    logger.info("🔧 Ручная проверка истекших кодов...")
    await check_expired_codes(bot)