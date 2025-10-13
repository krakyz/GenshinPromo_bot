"""
Исправленный scheduler.py с корректными функциями для main.py
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List
from aiogram import Bot

from database import db
from models import CodeModel
from utils.date_utils import get_moscow_time

logger = logging.getLogger(__name__)


class SchedulerService:
    """Планировщик для автоматических задач бота"""
    
    def __init__(self, bot: Bot):
        self.bot = bot
        self.is_running = False
        self.check_interval = 300  # Проверка каждые 5 минут
        
    async def start(self):
        """Запуск планировщика"""
        if self.is_running:
            logger.warning("Планировщик уже запущен")
            return
        
        self.is_running = True
        logger.info("🚀 Планировщик задач запущен")
        
        # Запускаем основной цикл планировщика
        await self._run_scheduler()
    
    async def stop(self):
        """Остановка планировщика"""
        self.is_running = False
        logger.info("⏹️ Планировщик задач остановлен")
    
    async def _run_scheduler(self):
        """Основной цикл планировщика"""
        while self.is_running:
            try:
                await self._check_expired_codes()
                await asyncio.sleep(self.check_interval)
                
            except asyncio.CancelledError:
                logger.info("Планировщик отменен")
                break
            except Exception as e:
                logger.error(f"Ошибка в планировщике: {e}")
                # Продолжаем работу даже при ошибках
                await asyncio.sleep(60)
    
    async def _check_expired_codes(self):
        """Проверка и обработка истекших кодов"""
        try:
            expired_codes = await db.get_codes_to_expire()
            
            if not expired_codes:
                logger.debug("Истекших кодов не найдено")
                return
            
            logger.info(f"⏰ Найдено истекших кодов: {len(expired_codes)}")
            
            for code in expired_codes:
                await self._process_expired_code(code)
                # Пауза между обработкой кодов
                await asyncio.sleep(2)
                
        except Exception as e:
            logger.error(f"Ошибка при проверке истекших кодов: {e}")
    
    async def _process_expired_code(self, code: CodeModel):
        """Обработка одного истекшего кода"""
        try:
            logger.info(f"🔄 Обрабатываю истекший код: {code.code}")
            
            # 1. Обновляем сообщения пользователей
            from utils.broadcast import update_expired_code_messages
            await update_expired_code_messages(self.bot, code.code)
            
            # 2. Удаляем код из базы данных
            success = await db.expire_code(code.code)
            
            if success:
                logger.info(f"✅ Код {code.code} успешно деактивирован и сообщения обновлены")
            else:
                logger.warning(f"⚠️ Не удалось деактивировать код {code.code}")
                
        except Exception as e:
            logger.error(f"Ошибка при обработке истекшего кода {code.code}: {e}")
    
    async def force_check_expired_codes(self):
        """Принудительная проверка истекших кодов (для тестирования)"""
        logger.info("🔍 Принудительная проверка истекших кодов...")
        await self._check_expired_codes()
    
    async def get_scheduler_status(self) -> dict:
        """Получение статуса планировщика"""
        moscow_now = get_moscow_time()
        
        return {
            'is_running': self.is_running,
            'check_interval_minutes': self.check_interval // 60,
            'current_time': moscow_now.strftime('%d.%m.%Y %H:%M МСК'),
            'next_check_in': f"{self.check_interval // 60} минут"
        }


# Глобальный экземпляр планировщика
scheduler_service: SchedulerService = None


async def init_scheduler(bot: Bot) -> SchedulerService:
    """
    Инициализация планировщика
    
    Args:
        bot: Экземпляр бота
        
    Returns:
        SchedulerService: Инициализированный планировщик
    """
    global scheduler_service
    
    scheduler_service = SchedulerService(bot)
    logger.info("📅 Планировщик инициализирован")
    
    return scheduler_service


async def start_scheduler_background(scheduler: SchedulerService):
    """
    Запуск планировщика в фоновом режиме
    
    Args:
        scheduler: Экземпляр планировщика
    """
    try:
        await scheduler.start()
    except asyncio.CancelledError:
        logger.info("📅 Планировщик отменен")
        await scheduler.stop()
    except Exception as e:
        logger.error(f"❌ Ошибка в планировщике: {e}")


async def stop_scheduler():
    """Остановка планировщика"""
    global scheduler_service
    if scheduler_service:
        await scheduler_service.stop()
        logger.info("📅 Планировщик остановлен")


# Функции для обратной совместимости с старым кодом

async def start_scheduler():
    """
    Старая функция start_scheduler без параметров
    (для совместимости со старым main.py)
    """
    logger.warning("⚠️ Вызвана устаревшая функция start_scheduler(). Используйте init_scheduler() и start_scheduler_background()")
    
    if scheduler_service:
        await scheduler_service.start()
    else:
        logger.error("❌ Планировщик не инициализирован. Вызовите init_scheduler(bot) сначала")


# Вспомогательные функции для тестирования

async def manual_expire_check(bot: Bot):
    """Ручная проверка истекших кодов (для разработки)"""
    temp_scheduler = SchedulerService(bot)
    await temp_scheduler.force_check_expired_codes()


async def get_scheduler_info() -> dict:
    """Получение информации о планировщике"""
    global scheduler_service
    if scheduler_service:
        return await scheduler_service.get_scheduler_status()
    else:
        return {
            'is_running': False,
            'error': 'Планировщик не инициализирован'
        }