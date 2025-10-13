"""
Оптимизированный планировщик задач с улучшенной обработкой ошибок
"""
import asyncio
import logging
from typing import Optional
from aiogram import Bot

from database import db
from utils.date_utils import get_moscow_time
from utils.broadcast import update_expired_code_messages

logger = logging.getLogger(__name__)


class SchedulerService:
    """Сервис планировщика для автоматических задач"""
    
    def __init__(self, bot: Bot, check_interval: int = 300):
        self.bot = bot
        self.check_interval = check_interval  # 5 минут по умолчанию
        self.is_running = False
        self.task: Optional[asyncio.Task] = None
    
    async def check_expired_codes(self) -> int:
        """
        Проверяет и обрабатывает истекшие коды
        Возвращает количество обработанных кодов
        """
        try:
            moscow_now = get_moscow_time()
            logger.info(f"🔍 Проверка истекших кодов: {moscow_now.strftime('%d.%m.%Y %H:%M:%S')}")
            
            # Получаем коды к истечению
            codes_to_expire = await db.get_codes_to_expire()
            
            if not codes_to_expire:
                logger.debug("Истекших кодов не найдено")
                return 0
            
            logger.info(f"Найдено истекших кодов: {len(codes_to_expire)}")
            
            expired_count = 0
            for code in codes_to_expire:
                try:
                    logger.info(f"⏰ Обрабатываю истекший код: {code.code}")
                    
                    # Обновляем сообщения пользователей ПЕРЕД удалением
                    await update_expired_code_messages(self.bot, code.code)
                    
                    # Удаляем код из БД
                    success = await db.expire_code_by_id(code.id)
                    
                    if success:
                        logger.info(f"✅ Код {code.code} успешно удален")
                        expired_count += 1
                    else:
                        logger.warning(f"⚠️ Не удалось удалить код {code.code}")
                    
                    # Небольшая пауза между обработкой кодов
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка обработки кода {code.code}: {e}")
                    continue
            
            if expired_count > 0:
                logger.info(f"🗑️ Обработано истекших кодов: {expired_count}")
            
            return expired_count
            
        except Exception as e:
            logger.error(f"💥 Критическая ошибка при проверке истекших кодов: {e}")
            return 0
    
    async def run_scheduler_cycle(self):
        """Один цикл планировщика"""
        try:
            moscow_time = get_moscow_time()
            logger.debug(f"🔄 Цикл планировщика: {moscow_time.strftime('%d.%m.%Y %H:%M:%S')}")
            
            # Проверяем истекшие коды
            await self.check_expired_codes()
            
            # Здесь можно добавить другие периодические задачи
            # await self.cleanup_old_messages()
            # await self.send_daily_stats()
            
        except Exception as e:
            logger.error(f"❌ Ошибка в цикле планировщика: {e}")
    
    async def start(self):
        """Запускает планировщик"""
        if self.is_running:
            logger.warning("⚠️ Планировщик уже запущен")
            return
        
        self.is_running = True
        moscow_time = get_moscow_time()
        logger.info(f"🚀 Планировщик запущен: {moscow_time.strftime('%d.%m.%Y %H:%M:%S')}")
        
        while self.is_running:
            try:
                await self.run_scheduler_cycle()
                await asyncio.sleep(self.check_interval)
                
            except asyncio.CancelledError:
                logger.info("⏹️ Планировщик остановлен по запросу")
                break
                
            except Exception as e:
                logger.error(f"💥 Неожиданная ошибка планировщика: {e}")
                await asyncio.sleep(60)  # Ждем минуту при ошибке
    
    def stop(self):
        """Останавливает планировщик"""
        logger.info("🛑 Остановка планировщика...")
        self.is_running = False
        
        if self.task and not self.task.done():
            self.task.cancel()


# Глобальная функция для обратной совместимости
async def check_expired_codes(bot: Bot):
    """
    Устаревшая функция - используется для обратной совместимости
    Рекомендуется использовать SchedulerService
    """
    scheduler = SchedulerService(bot)
    await scheduler.check_expired_codes()


async def start_scheduler(bot: Bot):
    """
    Запускает планировщик задач
    """
    scheduler = SchedulerService(bot, check_interval=300)  # 5 минут
    
    try:
        await scheduler.start()
    except Exception as e:
        logger.error(f"💥 Критическая ошибка планировщика: {e}")
    finally:
        scheduler.stop()


# Дополнительные планировщики для будущих задач
class MaintenanceScheduler:
    """Планировщик задач обслуживания"""
    
    def __init__(self, bot: Bot):
        self.bot = bot
    
    async def cleanup_old_messages(self):
        """Очистка старых сообщений (будущая функция)"""
        logger.info("🧹 Очистка старых сообщений...")
        # TODO: Реализовать очистку старых записей code_messages
        
    async def send_daily_stats(self):
        """Отправка дневной статистики админу (будущая функция)"""
        logger.info("📊 Отправка дневной статистики...")
        # TODO: Реализовать отправку статистики
    
    async def backup_database(self):
        """Создание резервной копии БД (будущая функция)"""
        logger.info("💾 Создание резервной копии БД...")
        # TODO: Реализовать бэкап БД


# Утилитарные функции для отладки
async def run_manual_cleanup(bot: Bot):
    """Ручная очистка для тестирования"""
    logger.info("🔧 Ручная очистка истекших кодов...")
    scheduler = SchedulerService(bot)
    count = await scheduler.check_expired_codes()
    logger.info(f"✅ Обработано кодов: {count}")
    return count