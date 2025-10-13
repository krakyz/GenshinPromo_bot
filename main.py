"""
Инициализация системы обновления сообщений для main.py
"""
import asyncio
import logging
from database import db

logger = logging.getLogger(__name__)


async def init_message_update_system():
    """
    Инициализирует систему обновления сообщений при запуске бота
    
    Добавьте вызов этой функции в main.py перед запуском бота:
    
    from utils.message_system import init_message_update_system
    
    async def main():
        await init_message_update_system()  # Добавить эту строку
        await dp.start_polling(bot)
    """
    
    try:
        logger.info("🔧 Инициализирую систему обновления сообщений...")
        
        # Создаем таблицу code_messages если её нет
        async with db.connection() if hasattr(db, 'connection') else db.get_connection() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS code_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    code_value TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (code_id) REFERENCES codes (id),
                    FOREIGN KEY (user_id) REFERENCES users (user_id),
                    UNIQUE(user_id, message_id)
                )
            """)
            await conn.commit()
        
        # Добавляем методы к объекту db если их еще нет
        if not hasattr(db, 'save_code_messages'):
            logger.info("Добавляю методы работы с сообщениями к базе данных...")
            await add_message_methods_to_db()
        
        logger.info("✅ Система обновления сообщений инициализирована")
        
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации системы сообщений: {e}")
        raise


async def add_message_methods_to_db():
    """Добавляет методы работы с сообщениями к объекту db"""
    
    # Метод сохранения связей сообщений
    async def save_code_messages(code_id: int, sent_messages: list):
        """Сохраняет связи между кодом и отправленными сообщениями"""
        try:
            from utils.date_utils import get_moscow_time, serialize_moscow_datetime
            
            async with db.connection() if hasattr(db, 'connection') else db.get_connection() as conn:
                # Получаем значение кода
                cursor = await conn.execute("SELECT code FROM codes WHERE id = ?", (code_id,))
                code_row = await cursor.fetchone()
                
                if not code_row:
                    logger.error(f"Код с ID {code_id} не найден")
                    return False
                
                code_value = code_row[0]
                current_time = serialize_moscow_datetime(get_moscow_time())
                
                # Подготавливаем данные для batch insert
                insert_data = [
                    (code_id, user_id, message_id, code_value, current_time)
                    for user_id, message_id in sent_messages
                ]
                
                # Выполняем batch insert
                await conn.executemany("""
                    INSERT OR IGNORE INTO code_messages 
                    (code_id, user_id, message_id, code_value, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, insert_data)
                
                await conn.commit()
                logger.info(f"Сохранено {len(insert_data)} связей сообщений для кода {code_value}")
                return True
                
        except Exception as e:
            logger.error(f"Ошибка сохранения связей сообщений: {e}")
            return False
    
    # Метод получения сообщений по коду
    async def get_code_messages_by_code_value(code_value: str):
        """Получает все сообщения связанные с кодом"""
        try:
            async with db.connection() if hasattr(db, 'connection') else db.get_connection() as conn:
                cursor = await conn.execute("""
                    SELECT id, code_id, user_id, message_id, code_value, created_at
                    FROM code_messages 
                    WHERE UPPER(code_value) = UPPER(?)
                    ORDER BY created_at DESC
                """, (code_value,))
                
                rows = await cursor.fetchall()
                
                messages = []
                for row in rows:
                    messages.append({
                        'id': row[0],
                        'code_id': row[1],
                        'user_id': row[2],
                        'message_id': row[3],
                        'code_value': row[4],
                        'created_at': row[5]
                    })
                
                logger.debug(f"Найдено {len(messages)} сообщений для кода {code_value}")
                return messages
                
        except Exception as e:
            logger.error(f"Ошибка получения сообщений кода {code_value}: {e}")
            return []
    
    # Метод удаления записей сообщений
    async def delete_code_messages_by_code_value(code_value: str):
        """Удаляет все записи сообщений для конкретного кода"""
        try:
            async with db.connection() if hasattr(db, 'connection') else db.get_connection() as conn:
                cursor = await conn.execute("""
                    DELETE FROM code_messages 
                    WHERE UPPER(code_value) = UPPER(?)
                """, (code_value,))
                
                await conn.commit()
                deleted_count = cursor.rowcount
                
                logger.info(f"Удалено {deleted_count} записей сообщений для кода {code_value}")
                return True
                
        except Exception as e:
            logger.error(f"Ошибка удаления записей сообщений кода {code_value}: {e}")
            return False
    
    # Добавляем методы к объекту db
    db.save_code_messages = save_code_messages
    db.get_code_messages_by_code_value = get_code_messages_by_code_value
    db.delete_code_messages_by_code_value = delete_code_messages_by_code_value
    
    logger.info("Методы работы с сообщениями добавлены к базе данных")


# Дополнительная утилита для тестирования
async def test_message_system():
    """Тестирование системы (можно запустить вручную)"""
    logger.info("🧪 Тестирование системы обновления сообщений...")
    
    try:
        # Проверяем есть ли таблица code_messages
        async with db.connection() if hasattr(db, 'connection') else db.get_connection() as conn:
            cursor = await conn.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='code_messages'
            """)
            table_exists = await cursor.fetchone()
            
            if table_exists:
                logger.info("✅ Таблица code_messages найдена")
                
                # Считаем количество записей
                cursor = await conn.execute("SELECT COUNT(*) FROM code_messages")
                count = (await cursor.fetchone())[0]
                logger.info(f"📊 В таблице code_messages: {count} записей")
            else:
                logger.warning("⚠️ Таблица code_messages не найдена")
        
        # Проверяем методы базы данных
        if hasattr(db, 'save_code_messages'):
            logger.info("✅ Метод save_code_messages найден")
        else:
            logger.warning("⚠️ Метод save_code_messages не найден")
            
        if hasattr(db, 'get_code_messages_by_code_value'):
            logger.info("✅ Метод get_code_messages_by_code_value найден")
        else:
            logger.warning("⚠️ Метод get_code_messages_by_code_value не найден")
            
        logger.info("✅ Тестирование завершено")
        
    except Exception as e:
        logger.error(f"❌ Ошибка тестирования: {e}")


if __name__ == "__main__":
    # Запуск тестирования
    asyncio.run(test_message_system())