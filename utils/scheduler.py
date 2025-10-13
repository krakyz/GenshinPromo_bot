# ИСПРАВЛЕНИЯ ДЛЯ utils/scheduler.py
# Убедиться что планировщик корректно обновляет сообщения

"""
ИСПРАВЛЕННЫЙ ПЛАНИРОВЩИК С ОБНОВЛЕНИЕМ СООБЩЕНИЙ
"""

import asyncio
import logging
from typing import Optional
from aiogram import Bot
from database import db
from utils.date_utils import get_moscow_time

logger = logging.getLogger(__name__)

class SchedulerService:
    """Сервис планировщика для автоматических задач с обновлением сообщений"""
    
    def __init__(self, bot: Bot, check_interval: int = 300):
        self.bot = bot
        self.check_interval = check_interval  # 5 минут по умолчанию
        self.is_running = False
        self.task: Optional[asyncio.Task] = None
    
    async def check_expired_codes(self) -> int:
        """
        Проверяет и обрабатывает истекшие коды с обновлением сообщений
        Возвращает количество обработанных кодов
        """
        try:
            moscow_now = get_moscow_time()
            logger.info(f"🔍 Проверка истекших кодов: {moscow_now.strftime('%d.%m.%Y %H:%M:%S')}")
            
            # Получаем коды к истечению
            codes_to_expire = await db.get_codes_to_expire()
            
            if not codes_to_expire:
                logger.debug("✅ Истекших кодов не найдено")
                return 0
            
            logger.info(f"⏰ Найдено истекших кодов: {len(codes_to_expire)}")
            
            expired_count = 0
            for code in codes_to_expire:
                try:
                    logger.info(f"🗑️ Обрабатываю истекший код: {code.code}")
                    
                    # 1. СНАЧАЛА обновляем все сообщения пользователей с этим кодом
                    from utils.broadcast import update_expired_code_messages
                    await update_expired_code_messages(self.bot, code.code)
                    
                    # 2. ПОТОМ удаляем код из БД
                    success = await db.expire_code_by_id(code.id)
                    
                    if success:
                        logger.info(f"✅ Код {code.code} успешно деактивирован и сообщения обновлены")
                        expired_count += 1
                    else:
                        logger.warning(f"⚠️ Не удалось деактивировать код {code.code}")
                    
                    # Небольшая пауза между обработкой кодов
                    await asyncio.sleep(2)
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка обработки кода {code.code}: {e}")
                    continue
            
            if expired_count > 0:
                logger.info(f"🎯 Обработано истекших кодов: {expired_count}")
            
            return expired_count
            
        except Exception as e:
            logger.error(f"💥 Критическая ошибка при проверке истекших кодов: {e}")
            return 0
    
    async def cleanup_old_message_records(self) -> int:
        """
        Очищает старые записи сообщений (старше 30 дней)
        Возвращает количество очищенных записей
        """
        try:
            logger.info("🧹 Очистка старых записей сообщений...")
            
            # Получаем количество записей для очистки
            async with aiosqlite.connect(db.db_path) as conn:
                cursor = await conn.execute("""
                    SELECT COUNT(*) FROM code_messages 
                    WHERE created_at < datetime('now', '-30 days')
                """)
                old_count = (await cursor.fetchone())[0]
                
                if old_count == 0:
                    logger.debug("Старых записей для очистки не найдено")
                    return 0
                
                # Удаляем старые записи
                await conn.execute("""
                    DELETE FROM code_messages 
                    WHERE created_at < datetime('now', '-30 days')
                """)
                await conn.commit()
                
                logger.info(f"🗑️ Очищено старых записей сообщений: {old_count}")
                return old_count
                
        except Exception as e:
            logger.error(f"❌ Ошибка очистки старых записей: {e}")
            return 0
    
    async def run_scheduler_cycle(self):
        """Один цикл планировщика с полным набором задач"""
        try:
            moscow_time = get_moscow_time()
            logger.debug(f"🔄 Цикл планировщика: {moscow_time.strftime('%d.%m.%Y %H:%M:%S')}")
            
            # 1. Проверяем и обрабатываем истекшие коды
            expired_count = await self.check_expired_codes()
            
            # 2. Каждый час очищаем старые записи (проверяем минуты)
            if moscow_time.minute == 0:
                await self.cleanup_old_message_records()
            
            # 3. Здесь можно добавить другие периодические задачи
            # await self.send_daily_stats()
            # await self.backup_database()
            
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
        logger.info(f"⏰ Интервал проверки: {self.check_interval} секунд")
        
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
    return await scheduler.check_expired_codes()

async def start_scheduler(bot: Bot):
    """
    Запускает планировщик задач с обновлением сообщений
    """
    scheduler = SchedulerService(bot, check_interval=300)  # 5 минут
    
    try:
        logger.info("🎯 Запуск планировщика с системой обновления сообщений")
        await scheduler.start()
    except Exception as e:
        logger.error(f"💥 Критическая ошибка планировщика: {e}")
    finally:
        scheduler.stop()

# Дополнительные утилиты для отладки и тестирования
async def run_manual_cleanup(bot: Bot):
    """Ручная очистка для тестирования"""
    logger.info("🔧 Ручная проверка и обновление истекших кодов...")
    scheduler = SchedulerService(bot)
    count = await scheduler.check_expired_codes()
    logger.info(f"✅ Обработано кодов: {count}")
    return count

async def test_message_update_system(bot: Bot):
    """Тестирование системы обновления сообщений"""
    try:
        logger.info("🧪 Тестирование системы обновления сообщений...")
        
        # Получаем все активные коды
        codes = await db.get_active_codes()
        
        if not codes:
            logger.warning("❌ Нет активных кодов для тестирования")
            return False
        
        test_results = []
        for code in codes[:3]:  # Тестируем максимум 3 кода
            try:
                # Проверяем связанные сообщения
                messages = await db.get_code_messages_by_value(code.code)
                test_results.append({
                    'code': code.code,
                    'messages_count': len(messages),
                    'can_update': len(messages) > 0
                })
                
            except Exception as e:
                logger.error(f"Ошибка тестирования кода {code.code}: {e}")
                test_results.append({
                    'code': code.code,
                    'messages_count': 0,
                    'can_update': False,
                    'error': str(e)
                })
        
        # Выводим результаты
        logger.info("📊 Результаты тестирования системы обновлений:")
        for result in test_results:
            status = "✅" if result['can_update'] else "⚠️"
            logger.info(f"  {status} {result['code']}: {result['messages_count']} сообщений")
        
        working_codes = len([r for r in test_results if r['can_update']])
        logger.info(f"🎯 Система работает для {working_codes}/{len(test_results)} протестированных кодов")
        
        return working_codes > 0
        
    except Exception as e:
        logger.error(f"💥 Ошибка тестирования системы: {e}")
        return False

# Функция для восстановления планировщика при ошибках
async def recover_scheduler(bot: Bot, max_retries: int = 3):
    """Восстанавливает планировщик после критических ошибок"""
    for attempt in range(max_retries):
        try:
            logger.info(f"🔄 Попытка восстановления планировщика #{attempt + 1}")
            await start_scheduler(bot)
            break
        except Exception as e:
            logger.error(f"❌ Попытка #{attempt + 1} неудачна: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(60 * (attempt + 1))  # Увеличиваем задержку
            else:
                logger.error("💥 Не удалось восстановить планировщик после всех попыток")
                raise