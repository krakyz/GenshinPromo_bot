import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from datetime import datetime

from config import BOT_TOKEN
from database import db
from handlers import user, admin

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def check_expired_codes(bot: Bot):
    """Периодическая проверка истекших кодов"""
    while True:
        try:
            # Получаем коды, которые должны истечь
            codes_to_expire = await db.get_codes_to_expire()
            
            for code in codes_to_expire:
                logger.info(f"Автоматически истекает код: {code.code}")
                
                # Помечаем код как истекший
                success = await db.expire_code_by_id(code.id)
                
                if success:
                    # Обновляем все старые сообщения с этим кодом
                    from handlers.admin import update_expired_code_messages
                    await update_expired_code_messages(bot, code.code)
                    logger.info(f"Код {code.code} автоматически истек и сообщения обновлены")
                
                # Небольшая пауза между обработкой кодов
                await asyncio.sleep(1)
            
            # Проверяем каждые 5 минут
            await asyncio.sleep(300)
            
        except Exception as e:
            logger.error(f"Ошибка при проверке истекших кодов: {e}")
            await asyncio.sleep(60)  # При ошибке ждем минуту перед повтором

async def main():
    """Основная функция запуска бота"""
    
    # Инициализация бота и диспетчера
    bot = Bot(token=BOT_TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    
    # Подключение роутеров
    dp.include_router(user.router)
    dp.include_router(admin.router)
    
    # Инициализация базы данных
    await db.init_db()
    
    logger.info("Бот запущен с полным функционалом управления БД")
    
    # Запускаем фоновую задачу проверки истекших кодов
    expiry_task = asyncio.create_task(check_expired_codes(bot))
    
    try:
        # Запуск поллинга
        await dp.start_polling(bot)
    finally:
        # Отменяем фоновую задачу при остановке
        expiry_task.cancel()
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        raise