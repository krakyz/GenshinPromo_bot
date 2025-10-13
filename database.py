"""
Исправленные методы базы данных для работы с сообщениями кодов
"""
import aiosqlite
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from config import DATABASE_PATH

logger = logging.getLogger(__name__)


class DatabaseExtension:
    """Расширение для базы данных с методами для работы с сообщениями кодов"""
    
    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path
    
    async def save_message_batch(self, message_records: List[Dict[str, Any]]) -> bool:
        """Массовое сохранение записей о сообщениях"""
        if not message_records:
            return True
            
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Создаем таблицу если не существует
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS code_messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        code_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        message_id INTEGER NOT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        is_active BOOLEAN DEFAULT TRUE,
                        FOREIGN KEY (code_id) REFERENCES codes (id)
                    )
                """)
                
                # Массовая вставка записей
                insert_query = """
                    INSERT INTO code_messages (code_id, user_id, message_id, is_active)
                    VALUES (?, ?, ?, ?)
                """
                
                records_to_insert = [
                    (record['code_id'], record['user_id'], record['message_id'], record['is_active'])
                    for record in message_records
                ]
                
                await db.executemany(insert_query, records_to_insert)
                await db.commit()
                
                logger.info(f"Сохранено {len(records_to_insert)} записей о сообщениях")
                return True
                
        except Exception as e:
            logger.error(f"Ошибка массового сохранения сообщений: {e}")
            return False
    
    async def get_messages_by_code_value(self, code_value: str) -> List[Dict[str, Any]]:
        """Получает все активные сообщения для конкретного кода по его значению"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                
                query = """
                    SELECT cm.id, cm.code_id, cm.user_id, cm.message_id, cm.created_at
                    FROM code_messages cm
                    INNER JOIN codes c ON cm.code_id = c.id
                    WHERE c.code = ? AND cm.is_active = TRUE
                """
                
                async with db.execute(query, (code_value,)) as cursor:
                    rows = await cursor.fetchall()
                    
                    messages = []
                    for row in rows:
                        messages.append({
                            'id': row['id'],
                            'code_id': row['code_id'],
                            'user_id': row['user_id'],
                            'message_id': row['message_id'],
                            'created_at': row['created_at']
                        })
                    
                    logger.info(f"Найдено {len(messages)} активных сообщений для кода {code_value}")
                    return messages
                    
        except Exception as e:
            logger.error(f"Ошибка получения сообщений для кода {code_value}: {e}")
            return []
    
    async def get_messages_by_code_id(self, code_id: int) -> List[Dict[str, Any]]:
        """Получает все активные сообщения для конкретного кода по его ID"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                
                query = """
                    SELECT id, code_id, user_id, message_id, created_at
                    FROM code_messages
                    WHERE code_id = ? AND is_active = TRUE
                """
                
                async with db.execute(query, (code_id,)) as cursor:
                    rows = await cursor.fetchall()
                    
                    messages = []
                    for row in rows:
                        messages.append({
                            'id': row['id'],
                            'code_id': row['code_id'],
                            'user_id': row['user_id'],
                            'message_id': row['message_id'],
                            'created_at': row['created_at']
                        })
                    
                    logger.info(f"Найдено {len(messages)} активных сообщений для кода ID {code_id}")
                    return messages
                    
        except Exception as e:
            logger.error(f"Ошибка получения сообщений для кода ID {code_id}: {e}")
            return []
    
    async def deactivate_messages_by_code_value(self, code_value: str) -> bool:
        """Помечает все сообщения кода как неактивные"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                query = """
                    UPDATE code_messages 
                    SET is_active = FALSE
                    WHERE code_id IN (
                        SELECT id FROM codes WHERE code = ?
                    )
                """
                
                await db.execute(query, (code_value,))
                await db.commit()
                
                logger.info(f"Сообщения для кода {code_value} помечены как неактивные")
                return True
                
        except Exception as e:
            logger.error(f"Ошибка деактивации сообщений для кода {code_value}: {e}")
            return False
    
    async def deactivate_messages_by_code_id(self, code_id: int) -> bool:
        """Помечает все сообщения кода как неактивные по ID"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                query = """
                    UPDATE code_messages 
                    SET is_active = FALSE
                    WHERE code_id = ?
                """
                
                await db.execute(query, (code_id,))
                await db.commit()
                
                logger.info(f"Сообщения для кода ID {code_id} помечены как неактивные")
                return True
                
        except Exception as e:
            logger.error(f"Ошибка деактивации сообщений для кода ID {code_id}: {e}")
            return False
    
    async def save_code_message(self, code_id: int, user_id: int, message_id: int) -> bool:
        """Сохраняет одну запись о сообщении (для обратной совместимости)"""
        return await self.save_message_batch([{
            'code_id': code_id,
            'user_id': user_id,
            'message_id': message_id,
            'is_active': True
        }])
    
    async def cleanup_inactive_messages(self, days_old: int = 30) -> int:
        """Удаляет старые неактивные сообщения"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                query = """
                    DELETE FROM code_messages 
                    WHERE is_active = FALSE 
                    AND created_at < datetime('now', '-{} days')
                """.format(days_old)
                
                cursor = await db.execute(query)
                deleted_count = cursor.rowcount
                await db.commit()
                
                logger.info(f"Удалено {deleted_count} старых неактивных записей сообщений")
                return deleted_count
                
        except Exception as e:
            logger.error(f"Ошибка очистки старых сообщений: {e}")
            return 0
    
    async def get_message_stats(self) -> Dict[str, int]:
        """Получает статистику по сообщениям"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Общее количество сообщений
                cursor = await db.execute("SELECT COUNT(*) FROM code_messages")
                total_messages = (await cursor.fetchone())[0]
                
                # Активные сообщения
                cursor = await db.execute("SELECT COUNT(*) FROM code_messages WHERE is_active = TRUE")
                active_messages = (await cursor.fetchone())[0]
                
                # Неактивные сообщения
                cursor = await db.execute("SELECT COUNT(*) FROM code_messages WHERE is_active = FALSE")
                inactive_messages = (await cursor.fetchone())[0]
                
                return {
                    'total': total_messages,
                    'active': active_messages,
                    'inactive': inactive_messages
                }
                
        except Exception as e:
            logger.error(f"Ошибка получения статистики сообщений: {e}")
            return {'total': 0, 'active': 0, 'inactive': 0}
    
    async def init_code_messages_table(self):
        """Инициализирует таблицу сообщений кодов"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS code_messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        code_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        message_id INTEGER NOT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        is_active BOOLEAN DEFAULT TRUE,
                        FOREIGN KEY (code_id) REFERENCES codes (id)
                    )
                """)
                
                # Создаем индексы для производительности
                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_code_messages_code_id 
                    ON code_messages(code_id)
                """)
                
                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_code_messages_active 
                    ON code_messages(is_active)
                """)
                
                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_code_messages_user_id 
                    ON code_messages(user_id)
                """)
                
                await db.commit()
                logger.info("Таблица code_messages инициализирована")
                
        except Exception as e:
            logger.error(f"Ошибка инициализации таблицы code_messages: {e}")


# Интеграция с существующей системой БД
class DatabaseManager(DatabaseExtension):
    """Основной менеджер базы данных с расширенными возможностями"""
    
    def __init__(self, db_path: str):
        super().__init__(db_path)
        self.db_path = db_path
    
    async def initialize(self):
        """Инициализирует все таблицы"""
        await self.init_code_messages_table()
        
        # Здесь могут быть другие инициализации таблиц
        logger.info("База данных полностью инициализирована")


# Функции для прямого использования (адаптеры)
async def save_message_batch(message_records: List[Dict[str, Any]]) -> bool:
    """Адаптер для сохранения записей сообщений"""
    # Предполагаем что db уже импортирован и инициализирован
    if hasattr(db, 'save_message_batch'):
        return await db.save_message_batch(message_records)
    else:
        # Создаем временный экземпляр
        db_ext = DatabaseExtension(db.db_path)
        return await db_ext.save_message_batch(message_records)


async def get_messages_by_code_value(code_value: str) -> List[Dict[str, Any]]:
    """Адаптер для получения сообщений по значению кода"""
    if hasattr(db, 'get_messages_by_code_value'):
        return await db.get_messages_by_code_value(code_value)
    else:
        db_ext = DatabaseExtension(db.db_path)
        return await db_ext.get_messages_by_code_value(code_value)


async def deactivate_messages_by_code_value(code_value: str) -> bool:
    """Адаптер для деактивации сообщений по значению кода"""
    if hasattr(db, 'deactivate_messages_by_code_value'):
        return await db.deactivate_messages_by_code_value(code_value)
    else:
        db_ext = DatabaseExtension(db.db_path)
        return await db_ext.deactivate_messages_by_code_value(code_value)