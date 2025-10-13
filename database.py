"""
Дополнения к database.py для работы с сообщениями кодов
"""
import aiosqlite
import logging
from typing import List, Dict, Any, Optional, Tuple
from models import CodeModel, UserModel, CodeMessageModel
from utils.date_utils import get_moscow_time, serialize_moscow_datetime, deserialize_moscow_datetime

logger = logging.getLogger(__name__)


class DatabaseExtended:
    """Расширенные методы базы данных для работы с сообщениями"""
    
    def __init__(self, db_path: str = "genshin_codes.db"):
        self.db_path = db_path
    
    async def init_code_messages_table(self):
        """Инициализация таблицы code_messages если её нет"""
        async with aiosqlite.connect(self.db_path) as conn:
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
            logger.info("Таблица code_messages инициализирована")
    
    async def save_code_messages(self, code_id: int, sent_messages: List[Tuple[int, int]]):
        """
        Сохраняет связи между кодом и отправленными сообщениями
        
        Args:
            code_id: ID кода в базе данных
            sent_messages: List[(user_id, message_id)]
        """
        try:
            # Сначала получаем значение кода для удобства поиска
            async with aiosqlite.connect(self.db_path) as conn:
                cursor = await conn.execute("SELECT code FROM codes WHERE id = ?", (code_id,))
                code_row = await cursor.fetchone()
                
                if not code_row:
                    logger.error(f"Код с ID {code_id} не найден")
                    return False
                
                code_value = code_row[0]
                current_time = serialize_moscow_datetime(get_moscow_time())
                
                # Подготавливаем данные для bulk insert
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
                
                # Проверяем сколько записей добавлено
                rows_affected = conn.total_changes
                logger.info(f"Сохранено {len(insert_data)} связей сообщений для кода {code_value}")
                
                return True
                
        except Exception as e:
            logger.error(f"Ошибка сохранения связей сообщений: {e}")
            return False
    
    async def get_code_messages_by_code_value(self, code_value: str) -> List[Dict[str, Any]]:
        """
        Получает все сообщения связанные с кодом по его значению
        
        Args:
            code_value: значение промо-кода (например, "GIFTCODE")
            
        Returns:
            List[Dict] со структурой: [{id, code_id, user_id, message_id, code_value, created_at}]
        """
        try:
            async with aiosqlite.connect(self.db_path) as conn:
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
                        'created_at': deserialize_moscow_datetime(row[5]) if row[5] else None
                    })
                
                logger.debug(f"Найдено {len(messages)} сообщений для кода {code_value}")
                return messages
                
        except Exception as e:
            logger.error(f"Ошибка получения сообщений кода {code_value}: {e}")
            return []
    
    async def get_code_messages_by_user(self, user_id: int) -> List[Dict[str, Any]]:
        """Получает все сообщения с кодами для конкретного пользователя"""
        try:
            async with aiosqlite.connect(self.db_path) as conn:
                cursor = await conn.execute("""
                    SELECT id, code_id, user_id, message_id, code_value, created_at
                    FROM code_messages 
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                """, (user_id,))
                
                rows = await cursor.fetchall()
                
                messages = []
                for row in rows:
                    messages.append({
                        'id': row[0],
                        'code_id': row[1],
                        'user_id': row[2],
                        'message_id': row[3],
                        'code_value': row[4],
                        'created_at': deserialize_moscow_datetime(row[5]) if row[5] else None
                    })
                
                return messages
                
        except Exception as e:
            logger.error(f"Ошибка получения сообщений пользователя {user_id}: {e}")
            return []
    
    async def delete_code_messages_by_code_value(self, code_value: str) -> bool:
        """Удаляет все записи сообщений для конкретного кода"""
        try:
            async with aiosqlite.connect(self.db_path) as conn:
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
    
    async def delete_code_messages_by_user(self, user_id: int) -> bool:
        """Удаляет все записи сообщений для конкретного пользователя"""
        try:
            async with aiosqlite.connect(self.db_path) as conn:
                cursor = await conn.execute("""
                    DELETE FROM code_messages 
                    WHERE user_id = ?
                """, (user_id,))
                
                await conn.commit()
                deleted_count = cursor.rowcount
                
                logger.info(f"Удалено {deleted_count} записей сообщений для пользователя {user_id}")
                return True
                
        except Exception as e:
            logger.error(f"Ошибка удаления записей сообщений пользователя {user_id}: {e}")
            return False
    
    async def get_expired_codes_with_messages(self) -> List[str]:
        """Получает список кодов, которые истекли, но у которых есть сообщения"""
        try:
            async with aiosqlite.connect(self.db_path) as conn:
                cursor = await conn.execute("""
                    SELECT DISTINCT cm.code_value
                    FROM code_messages cm
                    LEFT JOIN codes c ON cm.code_id = c.id
                    WHERE c.id IS NULL
                    ORDER BY cm.code_value
                """)
                
                rows = await cursor.fetchall()
                codes = [row[0] for row in rows]
                
                logger.info(f"Найдено {len(codes)} истекших кодов с сообщениями")
                return codes
                
        except Exception as e:
            logger.error(f"Ошибка получения истекших кодов: {e}")
            return []
    
    async def get_code_messages_stats(self) -> Dict[str, int]:
        """Получает статистику по сообщениям кодов"""
        try:
            async with aiosqlite.connect(self.db_path) as conn:
                # Общее количество записей
                cursor = await conn.execute("SELECT COUNT(*) FROM code_messages")
                total_messages = (await cursor.fetchone())[0]
                
                # Количество уникальных кодов
                cursor = await conn.execute("SELECT COUNT(DISTINCT code_value) FROM code_messages")
                unique_codes = (await cursor.fetchone())[0]
                
                # Количество уникальных пользователей
                cursor = await conn.execute("SELECT COUNT(DISTINCT user_id) FROM code_messages")
                unique_users = (await cursor.fetchone())[0]
                
                return {
                    'total_messages': total_messages,
                    'unique_codes': unique_codes,
                    'unique_users': unique_users
                }
                
        except Exception as e:
            logger.error(f"Ошибка получения статистики сообщений: {e}")
            return {'total_messages': 0, 'unique_codes': 0, 'unique_users': 0}
    
    async def cleanup_old_code_messages(self, days_old: int = 30) -> int:
        """
        Очищает старые записи сообщений (старше указанного количества дней)
        
        Returns:
            количество удаленных записей
        """
        try:
            from datetime import timedelta
            cutoff_date = get_moscow_time() - timedelta(days=days_old)
            cutoff_str = serialize_moscow_datetime(cutoff_date)
            
            async with aiosqlite.connect(self.db_path) as conn:
                cursor = await conn.execute("""
                    DELETE FROM code_messages 
                    WHERE created_at < ?
                """, (cutoff_str,))
                
                await conn.commit()
                deleted_count = cursor.rowcount
                
                logger.info(f"Удалено {deleted_count} старых записей сообщений (старше {days_old} дней)")
                return deleted_count
                
        except Exception as e:
            logger.error(f"Ошибка очистки старых сообщений: {e}")
            return 0


# Расширяем основной класс базы данных
async def extend_database_with_messages():
    """Расширяет существующую базу данных функциями работы с сообщениями"""
    try:
        # Импортируем основную базу данных
        from database import db
        
        # Добавляем методы расширения
        extended_db = DatabaseExtended(db.db_path)
        
        # Инициализируем таблицу сообщений
        await extended_db.init_code_messages_table()
        
        # Добавляем методы к основному объекту db
        db.save_code_messages = extended_db.save_code_messages
        db.get_code_messages_by_code_value = extended_db.get_code_messages_by_code_value
        db.get_code_messages_by_user = extended_db.get_code_messages_by_user
        db.delete_code_messages_by_code_value = extended_db.delete_code_messages_by_code_value
        db.delete_code_messages_by_user = extended_db.delete_code_messages_by_user
        db.get_expired_codes_with_messages = extended_db.get_expired_codes_with_messages
        db.get_code_messages_stats = extended_db.get_code_messages_stats
        db.cleanup_old_code_messages = extended_db.cleanup_old_code_messages
        
        logger.info("База данных расширена функциями работы с сообщениями")
        
    except Exception as e:
        logger.error(f"Ошибка расширения базы данных: {e}")


# Функция инициализации для добавления в main.py
async def init_message_system():
    """Инициализирует систему сообщений при запуске бота"""
    await extend_database_with_messages()
    logger.info("Система сообщений инициализирована")