import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from database import db
from handlers.user import router as user_router
from handlers.admin import router as admin_router
from utils.scheduler import start_scheduler

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
    logger.info("Запуск бота Genshin Impact промо-кодов...")
    
    # Инициализация бота и диспетчера
    bot = Bot(token=BOT_TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    
    # Подключение роутеров
    dp.include_router(user_router)
    dp.include_router(admin_router)
    
    # Инициализация базы данных
    await db.init_db()
    logger.info("База данных инициализирована")
    
    # Запуск планировщика проверки истекших кодов
    scheduler_task = asyncio.create_task(start_scheduler(bot))
    
    try:
        logger.info("Бот запущен и готов к работе")
        await dp.start_polling(bot)
    finally:
        scheduler_task.cancel()
        await bot.session.close()
        logger.info("Бот остановлен")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        raise