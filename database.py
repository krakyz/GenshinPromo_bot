import aiosqlite
import logging
from typing import List, Optional, Tuple
from datetime import datetime
from models import CodeModel, UserModel, CodeMessageModel
from config import DATABASE_PATH
from utils.date_utils import get_moscow_time, serialize_moscow_datetime, deserialize_moscow_datetime
import os

logger = logging.getLogger(__name__)

class Database:
    """Класс для работы с базой данных SQLite"""
    
    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path
    
    async def init_db(self):
        """Инициализация базы данных"""
        async with aiosqlite.connect(self.db_path) as db:
            # Таблица для промо-кодов
            await db.execute('''
                CREATE TABLE IF NOT EXISTS codes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE NOT NULL,
                    description TEXT,
                    rewards TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expired_at TIMESTAMP,
                    expires_date TIMESTAMP
                )
            ''')
            
            # Таблица для пользователей
            await db.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER UNIQUE NOT NULL,
                    username TEXT,
                    first_name TEXT,
                    is_subscribed BOOLEAN DEFAULT 1,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица для отслеживания сообщений с кодами
            await db.execute('''
                CREATE TABLE IF NOT EXISTS code_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (code_id) REFERENCES codes (id)
                )
            ''')
            
            await db.commit()
            logger.info("База данных инициализирована")
    
    async def add_code(self, code: CodeModel) -> Optional[int]:
        """Добавить новый промо-код и вернуть его ID"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Сериализуем даты для хранения в UTC
                expires_date_str = None
                if code.expires_date:
                    expires_date_str = serialize_moscow_datetime(code.expires_date)
                
                cursor = await db.execute('''
                    INSERT INTO codes (code, description, rewards, is_active, created_at, expired_at, expires_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    code.code,
                    code.description,
                    code.rewards,
                    code.is_active,
                    datetime.utcnow().isoformat() if code.created_at else datetime.utcnow().isoformat(),
                    code.expired_at,
                    expires_date_str
                ))
                await db.commit()
                code_id = cursor.lastrowid
                logger.info(f"Добавлен новый код: {code.code} (ID: {code_id}), expires_date: {expires_date_str}")
                return code_id
        except aiosqlite.IntegrityError:
            logger.warning(f"Код {code.code} уже существует")
            return None
        except Exception as e:
            logger.error(f"Ошибка при добавлении кода: {e}")
            return None
    
    async def get_active_codes(self) -> List[CodeModel]:
        """Получить все активные промо-коды"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute('''
                SELECT id, code, description, rewards, is_active, created_at, expired_at, expires_date
                FROM codes
                WHERE is_active = 1
                ORDER BY created_at DESC
            ''') as cursor:
                rows = await cursor.fetchall()
                codes = []
                for row in rows:
                    # Десериализация дат
                    created_at = None
                    if row[5]:
                        try:
                            created_at = datetime.fromisoformat(row[5])
                        except:
                            created_at = None
                    
                    expired_at = None
                    if row[6]:
                        try:
                            expired_at = datetime.fromisoformat(row[6])
                        except:
                            expired_at = None
                    
                    expires_date = None
                    if row[7]:
                        expires_date = deserialize_moscow_datetime(row[7])
                    
                    code_model = CodeModel(
                        id=row[0],
                        code=row[1],
                        description=row[2],
                        rewards=row[3],
                        is_active=bool(row[4]),
                        created_at=created_at,
                        expired_at=expired_at,
                        expires_date=expires_date
                    )
                    codes.append(code_model)
                    logger.debug(f"Загружен код: {code_model.code}, expires_date: {code_model.expires_date}")
                
                logger.info(f"Найдено активных кодов: {len(codes)}")
                return codes
    
    async def get_codes_to_expire(self) -> List[CodeModel]:
        """Получить коды, которые должны истечь (по московскому времени)"""
        moscow_now = get_moscow_time()
        
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute('''
                SELECT id, code, description, rewards, is_active, created_at, expired_at, expires_date
                FROM codes
                WHERE is_active = 1 AND expires_date IS NOT NULL
            ''') as cursor:
                rows = await cursor.fetchall()
                codes_to_expire = []
                
                for row in rows:
                    expires_date = None
                    if row[7]:
                        expires_date = deserialize_moscow_datetime(row[7])
                        
                        # Проверяем, истек ли код
                        if expires_date and moscow_now >= expires_date:
                            code_model = CodeModel(
                                id=row[0],
                                code=row[1],
                                description=row[2],
                                rewards=row[3],
                                is_active=bool(row[4]),
                                created_at=datetime.fromisoformat(row[5]) if row[5] else None,
                                expired_at=datetime.fromisoformat(row[6]) if row[6] else None,
                                expires_date=expires_date
                            )
                            codes_to_expire.append(code_model)
                            logger.debug(f"Код к истечению: {code_model.code}, истекает: {expires_date}")
                
                logger.info(f"Найдено кодов для истечения: {len(codes_to_expire)}")
                return codes_to_expire
    
    async def delete_code_completely(self, code: str) -> bool:
        """ПОЛНОСТЬЮ УДАЛИТЬ код из базы данных (необратимо)"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Сначала получаем ID кода
                async with db.execute('SELECT id FROM codes WHERE code = ?', (code,)) as cursor:
                    row = await cursor.fetchone()
                    if not row:
                        logger.warning(f"Код {code} не найден для удаления")
                        return False
                    
                    code_id = row[0]
                
                # Удаляем связанные сообщения
                await db.execute('DELETE FROM code_messages WHERE code_id = ?', (code_id,))
                
                # Удаляем сам код
                cursor = await db.execute('DELETE FROM codes WHERE code = ?', (code,))
                await db.commit()
                
                if cursor.rowcount > 0:
                    logger.info(f"Код {code} ПОЛНОСТЬЮ УДАЛЕН из базы данных")
                    return True
                else:
                    logger.warning(f"Код {code} не найден для удаления")
                    return False
        except Exception as e:
            logger.error(f"Ошибка при полном удалении кода: {e}")
            return False
    
    async def expire_code(self, code: str) -> bool:
        """Пометить код как истекший (старый метод - для совместимости)"""
        # Теперь используем полное удаление
        return await self.delete_code_completely(code)
    
    async def expire_code_by_id(self, code_id: int) -> bool:
        """Пометить код как истекший по ID (полное удаление)"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Получаем код по ID
                async with db.execute('SELECT code FROM codes WHERE id = ?', (code_id,)) as cursor:
                    row = await cursor.fetchone()
                    if not row:
                        logger.warning(f"Код с ID {code_id} не найден")
                        return False
                    
                    code = row[0]
                
                # Используем полное удаление
                return await self.delete_code_completely(code)
        except Exception as e:
            logger.error(f"Ошибка при удалении кода по ID: {e}")
            return False
    
    async def add_user(self, user: UserModel) -> bool:
        """Добавить нового пользователя"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('''
                    INSERT OR REPLACE INTO users (user_id, username, first_name, is_subscribed, joined_at)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    user.user_id,
                    user.username,
                    user.first_name,
                    user.is_subscribed,
                    user.joined_at
                ))
                await db.commit()
                logger.info(f"Пользователь {user.user_id} добавлен/обновлен")
                return True
        except Exception as e:
            logger.error(f"Ошибка при добавлении пользователя: {e}")
            return False
    
    async def get_all_subscribers(self) -> List[int]:
        """Получить всех подписчиков для рассылки"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute('''
                SELECT user_id FROM users WHERE is_subscribed = 1
            ''') as cursor:
                rows = await cursor.fetchall()
                return [row[0] for row in rows]
    
    async def get_user_stats(self) -> Tuple[int, int, List[dict]]:
        """Получить статистику пользователей: всего, подписчиков, последние 5"""
        async with aiosqlite.connect(self.db_path) as db:
            # Общее количество пользователей
            async with db.execute('SELECT COUNT(*) FROM users') as cursor:
                total_users = (await cursor.fetchone())[0]
            
            # Количество подписчиков
            async with db.execute('SELECT COUNT(*) FROM users WHERE is_subscribed = 1') as cursor:
                subscribers_count = (await cursor.fetchone())[0]
            
            # Последние 5 пользователей
            async with db.execute('''
                SELECT user_id, username, first_name, is_subscribed, joined_at
                FROM users
                ORDER BY joined_at DESC
                LIMIT 5
            ''') as cursor:
                recent_users_rows = await cursor.fetchall()
                recent_users = []
                for row in recent_users_rows:
                    recent_users.append({
                        'user_id': row[0],
                        'username': row[1],
                        'first_name': row[2],
                        'is_subscribed': bool(row[3]),
                        'joined_at': datetime.fromisoformat(row[4]) if row[4] else None
                    })
            
            return total_users, subscribers_count, recent_users
    
    async def subscribe_user(self, user_id: int) -> bool:
        """Подписать пользователя на рассылку"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('''
                    UPDATE users SET is_subscribed = 1 WHERE user_id = ?
                ''', (user_id,))
                await db.commit()
                logger.info(f"Пользователь {user_id} подписался на рассылку")
                return True
        except Exception as e:
            logger.error(f"Ошибка при подписке пользователя: {e}")
            return False
    
    async def unsubscribe_user(self, user_id: int) -> bool:
        """ОТПИСАТЬ пользователя от рассылки (только для команды /unsubscribe)"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('''
                    UPDATE users SET is_subscribed = 0 WHERE user_id = ?
                ''', (user_id,))
                await db.commit()
                logger.info(f"Пользователь {user_id} отписался от рассылки")
                return True
        except Exception as e:
            logger.error(f"Ошибка при отписке пользователя: {e}")
            return False
    
    async def save_code_message(self, code_id: int, user_id: int, message_id: int) -> bool:
        """Сохранить связь между кодом и отправленным сообщением"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('''
                    INSERT INTO code_messages (code_id, user_id, message_id, created_at)
                    VALUES (?, ?, ?, ?)
                ''', (code_id, user_id, message_id, datetime.utcnow().isoformat()))
                await db.commit()
                logger.debug(f"Сохранена связь: код {code_id}, пользователь {user_id}, сообщение {message_id}")
                return True
        except Exception as e:
            logger.error(f"Ошибка при сохранении связи сообщения: {e}")
            return False
    
    async def get_code_messages(self, code_id: int) -> List[CodeMessageModel]:
        """Получить все сообщения связанные с конкретным кодом"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute('''
                SELECT id, code_id, user_id, message_id, created_at
                FROM code_messages
                WHERE code_id = ?
            ''', (code_id,)) as cursor:
                rows = await cursor.fetchall()
                return [
                    CodeMessageModel(
                        id=row[0],
                        code_id=row[1],
                        user_id=row[2],
                        message_id=row[3],
                        created_at=datetime.fromisoformat(row[4]) if row[4] else None
                    )
                    for row in rows
                ]
    
    async def reset_database(self) -> bool:
        """Сброс базы данных (удаление всех данных кроме пользователей)"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('DELETE FROM code_messages')
                await db.execute('DELETE FROM codes')
                await db.execute('DELETE FROM sqlite_sequence WHERE name IN ("codes", "code_messages")')
                await db.commit()
                logger.info("База данных сброшена (пользователи сохранены)")
                return True
        except Exception as e:
            logger.error(f"Ошибка при сбросе базы данных: {e}")
            return False
    
    async def get_database_stats(self) -> dict:
        """Получить статистику базы данных (теперь только активные коды)"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                stats = {}
                
                async with db.execute('SELECT COUNT(*) FROM users') as cursor:
                    stats['users'] = (await cursor.fetchone())[0]
                
                # Теперь считаем только активные коды (неактивные удалены)
                async with db.execute('SELECT COUNT(*) FROM codes') as cursor:
                    stats['codes_total'] = (await cursor.fetchone())[0]
                    stats['codes_active'] = stats['codes_total']  # Все коды активные
                
                async with db.execute('SELECT COUNT(*) FROM code_messages') as cursor:
                    stats['messages'] = (await cursor.fetchone())[0]
                
                if os.path.exists(self.db_path):
                    size_bytes = os.path.getsize(self.db_path)
                    stats['file_size'] = f"{size_bytes / 1024:.1f} KB"
                else:
                    stats['file_size'] = "0 KB"
                
                return stats
        except Exception as e:
            logger.error(f"Ошибка при получении статистики БД: {e}")
            return {}

# Создаем глобальный экземпляр базы данных
db = Database()

"""
Дополнительные методы для database.py для работы с сообщениями
Этот код нужно добавить в существующий файл database.py
"""

# Добавить в класс Database эти методы:

async def save_code_message(self, message_model) -> bool:
    """Сохраняет связь между кодом и отправленным сообщением"""
    try:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO code_messages (code_id, user_id, message_id, created_at)
                VALUES (?, ?, ?, ?)
            """, (
                message_model.code_id,
                message_model.user_id, 
                message_model.message_id,
                serialize_moscow_datetime(message_model.created_at or datetime.now())
            ))
            await db.commit()
            logger.info(f"💾 Сохранена связь сообщения: код {message_model.code_id} -> {message_model.user_id}:{message_model.message_id}")
            return True
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения связи сообщения: {e}")
        return False


async def get_code_messages_by_value(self, code_value: str) -> List:
    """Получает все сообщения связанные с кодом по его значению"""
    try:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT cm.id, cm.code_id, cm.user_id, cm.message_id, cm.created_at
                FROM code_messages cm
                INNER JOIN codes c ON cm.code_id = c.id
                WHERE c.code = ? AND cm.is_active = 1
            """, (code_value.upper(),))
            
            rows = await cursor.fetchall()
            messages = []
            
            for row in rows:
                message = CodeMessageModel(
                    id=row[0],
                    code_id=row[1],
                    user_id=row[2],
                    message_id=row[3],
                    created_at=deserialize_moscow_datetime(row[4]) if row[4] else None
                )
                messages.append(message)
            
            logger.info(f"📨 Найдено сообщений для кода {code_value}: {len(messages)}")
            return messages
            
    except Exception as e:
        logger.error(f"❌ Ошибка получения сообщений для кода {code_value}: {e}")
        return []


async def get_code_messages_by_id(self, code_id: int) -> List:
    """Получает все сообщения связанные с кодом по ID"""
    try:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT id, code_id, user_id, message_id, created_at, is_active
                FROM code_messages
                WHERE code_id = ? AND is_active = 1
            """, (code_id,))
            
            rows = await cursor.fetchall()
            messages = []
            
            for row in rows:
                message = CodeMessageModel(
                    id=row[0],
                    code_id=row[1],
                    user_id=row[2],
                    message_id=row[3],
                    created_at=deserialize_moscow_datetime(row[4]) if row[4] else None,
                    is_active=bool(row[5])
                )
                messages.append(message)
            
            return messages
            
    except Exception as e:
        logger.error(f"❌ Ошибка получения сообщений для кода ID {code_id}: {e}")
        return []


async def delete_code_messages_by_code_id(self, code_id: int) -> int:
    """Удаляет все записи сообщений для кода"""
    try:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                DELETE FROM code_messages WHERE code_id = ?
            """, (code_id,))
            await db.commit()
            
            deleted_count = cursor.rowcount
            logger.info(f"🗑️ Удалено записей сообщений для кода {code_id}: {deleted_count}")
            return deleted_count
            
    except Exception as e:
        logger.error(f"❌ Ошибка удаления записей сообщений: {e}")
        return 0


async def mark_code_messages_inactive(self, code_id: int) -> int:
    """Помечает записи сообщений как неактивные (альтернатива удалению)"""
    try:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                UPDATE code_messages SET is_active = 0 WHERE code_id = ?
            """, (code_id,))
            await db.commit()
            
            updated_count = cursor.rowcount
            logger.info(f"📝 Помечено неактивными записей сообщений: {updated_count}")
            return updated_count
            
    except Exception as e:
        logger.error(f"❌ Ошибка обновления статуса сообщений: {e}")
        return 0


async def get_message_stats(self) -> Dict[str, int]:
    """Получает статистику сообщений"""
    try:
        async with aiosqlite.connect(self.db_path) as db:
            # Общее количество записей сообщений
            cursor = await db.execute("SELECT COUNT(*) FROM code_messages")
            total_messages = (await cursor.fetchone())[0]
            
            # Активные записи сообщений
            cursor = await db.execute("SELECT COUNT(*) FROM code_messages WHERE is_active = 1")
            active_messages = (await cursor.fetchone())[0]
            
            # Количество кодов с сообщениями
            cursor = await db.execute("""
                SELECT COUNT(DISTINCT code_id) FROM code_messages WHERE is_active = 1
            """)
            codes_with_messages = (await cursor.fetchone())[0]
            
            return {
                "total_messages": total_messages,
                "active_messages": active_messages,
                "codes_with_messages": codes_with_messages
            }
            
    except Exception as e:
        logger.error(f"❌ Ошибка получения статистики сообщений: {e}")
        return {"total_messages": 0, "active_messages": 0, "codes_with_messages": 0}


async def cleanup_orphaned_messages(self) -> int:
    """Очищает записи сообщений для несуществующих кодов"""
    try:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                DELETE FROM code_messages 
                WHERE code_id NOT IN (SELECT id FROM codes)
            """)
            await db.commit()
            
            deleted_count = cursor.rowcount
            logger.info(f"🧹 Очищено потерянных записей сообщений: {deleted_count}")
            return deleted_count
            
    except Exception as e:
        logger.error(f"❌ Ошибка очистки потерянных сообщений: {e}")
        return 0


# Также нужно обновить метод init_db() для создания таблицы code_messages:

async def init_db(self):
    """Инициализация базы данных с таблицей сообщений"""
    async with aiosqlite.connect(self.db_path) as db:
        # Существующие таблицы...
        
        # Таблица для отслеживания сообщений
        await db.execute("""
            CREATE TABLE IF NOT EXISTS code_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                is_active BOOLEAN DEFAULT 1,
                FOREIGN KEY (code_id) REFERENCES codes (id) ON DELETE CASCADE,
                UNIQUE(code_id, user_id, message_id)
            )
        """)
        
        # Индексы для оптимизации
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_code_messages_code_id 
            ON code_messages (code_id)
        """)
        
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_code_messages_user_id 
            ON code_messages (user_id)
        """)
        
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_code_messages_active 
            ON code_messages (is_active)
        """)
        
        await db.commit()
        logger.info("💾 Таблица code_messages инициализирована")