"""
Полностью исправленный main.py с корректным запуском планировщика
"""
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from database import db
from handlers.user import router as user_router
from handlers.admin import router as admin_router
from utils.scheduler import init_scheduler, start_scheduler_background

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

async def main():
    """Главная функция запуска бота"""
    logger.info("🚀 Запуск бота Genshin Impact промо-кодов...")
    
    # Инициализация бота и диспетчера
    bot = Bot(token=BOT_TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    
    # Подключение роутеров
    dp.include_router(user_router)
    dp.include_router(admin_router)
    
    # Инициализация базы данных
    try:
        await db.init_db()
        logger.info("✅ База данных инициализирована")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации БД: {e}")
        raise
    
    # Инициализация и запуск планировщика
    try:
        scheduler = await init_scheduler(bot)
        scheduler_task = asyncio.create_task(start_scheduler_background(scheduler))
        logger.info("📅 Планировщик запущен в фоновом режиме")
    except Exception as e:
        logger.error(f"❌ Ошибка запуска планировщика: {e}")
        scheduler_task = None
    
    try:
        logger.info("🤖 Бот запущен и готов к работе")
        await dp.start_polling(bot)
        
    except KeyboardInterrupt:
        logger.info("⏹️ Бот остановлен пользователем")
        
    except Exception as e:
        logger.error(f"💥 Критическая ошибка: {e}")
        raise
        
    finally:
        # Корректное завершение
        if scheduler_task and not scheduler_task.done():
            scheduler_task.cancel()
            try:
                await scheduler_task
            except asyncio.CancelledError:
                pass
        
        await bot.session.close()
        logger.info("✅ Бот корректно остановлен")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Программа остановлена пользователем")
    except Exception as e:
        logger.error(f"💥 Критическая ошибка: {e}")
        raise