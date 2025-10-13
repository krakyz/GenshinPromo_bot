"""
База данных с миграцией для добавления недостающей колонки code_value
"""
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
    """Класс для работы с SQLite базой данных с поддержкой миграций"""
    
    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path
        
    async def init_db(self):
        """Инициализация базы данных с созданием таблиц и выполнением миграций"""
        async with aiosqlite.connect(self.db_path) as db:
            # Таблица промо-кодов
            await db.execute('''
                CREATE TABLE IF NOT EXISTS codes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE NOT NULL,
                    description TEXT,
                    rewards TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expired_at TIMESTAMP,
                    expires_date TIMESTAMP  -- Планируемая дата истечения
                )
            ''')
            
            # Таблица пользователей
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
            
            # Таблица связей сообщений с кодами (базовая версия)
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
            
            # МИГРАЦИЯ: Добавляем колонку code_value если её нет
            await self._add_code_value_column(db)
            
            await db.commit()
            logger.info("База данных инициализирована с выполненными миграциями")
    
    async def _add_code_value_column(self, db):
        """Миграция: добавление колонки code_value в таблицу code_messages"""
        try:
            # Проверяем, существует ли колонка code_value
            cursor = await db.execute("PRAGMA table_info(code_messages)")
            columns = await cursor.fetchall()
            column_names = [column[1] for column in columns]
            
            if 'code_value' not in column_names:
                logger.info("🔄 Выполняю миграцию: добавление колонки code_value")
                
                # Добавляем новую колонку
                await db.execute('ALTER TABLE code_messages ADD COLUMN code_value TEXT')
                
                # Заполняем существующие записи значениями кодов
                await db.execute('''
                    UPDATE code_messages 
                    SET code_value = (
                        SELECT codes.code 
                        FROM codes 
                        WHERE codes.id = code_messages.code_id
                    )
                    WHERE code_value IS NULL
                ''')
                
                await db.commit()
                logger.info("✅ Миграция выполнена: колонка code_value добавлена и заполнена")
            else:
                logger.debug("Колонка code_value уже существует")
                
        except Exception as e:
            logger.error(f"Ошибка при выполнении миграции: {e}")
            # Не прерываем инициализацию из-за ошибки миграции

    async def add_code(self, code: CodeModel) -> Optional[int]:
        """Добавление нового промо-кода. Возвращает ID кода"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Подготавливаем дату истечения для сериализации
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
                
                logger.info(f"Добавлен код {code.code} с ID {code_id}, expires_date: {expires_date_str}")
                return code_id
                
        except aiosqlite.IntegrityError:
            logger.warning(f"Код {code.code} уже существует")
            return None
        except Exception as e:
            logger.error(f"Ошибка при добавлении кода: {e}")
            return None
    
    async def get_active_codes(self) -> List[CodeModel]:
        """Получение всех активных промо-кодов"""
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
                    # Парсим created_at (может быть в формате UTC)
                    created_at = None
                    if row[5]:
                        try:
                            created_at = datetime.fromisoformat(row[5])
                        except:
                            created_at = None
                    
                    # Парсим expired_at
                    expired_at = None
                    if row[6]:
                        try:
                            expired_at = datetime.fromisoformat(row[6])
                        except:
                            expired_at = None
                    
                    # Парсим expires_date
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
                    logger.debug(f"Загружен код {code_model.code}, expires_date: {code_model.expires_date}")
                
                logger.info(f"Загружено активных кодов: {len(codes)}")
                return codes
    
    async def get_codes_to_expire(self) -> List[CodeModel]:
        """Получение кодов, которые должны истечь"""
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
                        logger.debug(f"Код {code_model.code} истек, expires_date: {expires_date}")
                
                logger.info(f"Найдено истекших кодов: {len(codes_to_expire)}")
                return codes_to_expire
    
    async def delete_code_completely(self, code: str) -> bool:
        """Полное удаление кода и всех связанных данных"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Сначала получаем ID кода, если он есть
                async with db.execute("SELECT id FROM codes WHERE code = ?", (code,)) as cursor:
                    row = await cursor.fetchone()
                    if not row:
                        logger.warning(f"Код {code} не найден")
                        return False
                    
                    code_id = row[0]
                
                # Удаляем все связанные сообщения с кодом (с обработкой отсутствия code_value)
                try:
                    # Пробуем удалить по code_value (новая схема)
                    await db.execute("DELETE FROM code_messages WHERE code_value = ?", (code,))
                except aiosqlite.OperationalError:
                    # Если колонка code_value не существует, удаляем по code_id (старая схема)
                    logger.info("Удаляем сообщения по старой схеме (code_id)")
                    await db.execute("DELETE FROM code_messages WHERE code_id = ?", (code_id,))
                
                # Также удаляем по code_id для полной очистки
                await db.execute("DELETE FROM code_messages WHERE code_id = ?", (code_id,))
                
                # Удаляем сам код
                cursor = await db.execute("DELETE FROM codes WHERE code = ?", (code,))
                await db.commit()
                
                if cursor.rowcount > 0:
                    logger.info(f"Код {code} полностью удален вместе со связанными сообщениями")
                    return True
                else:
                    logger.warning(f"Код {code} не был удален")
                    return False
                    
        except Exception as e:
            logger.error(f"Ошибка при удалении кода: {e}")
            return False
    
    async def expire_code(self, code: str) -> bool:
        """Деактивация кода (алиас для полного удаления)"""
        return await self.delete_code_completely(code)
    
    async def expire_code_by_id(self, code_id: int) -> bool:
        """Деактивация кода по ID"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Получаем значение кода
                async with db.execute("SELECT code FROM codes WHERE id = ?", (code_id,)) as cursor:
                    row = await cursor.fetchone()
                    if not row:
                        logger.warning(f"Код с ID {code_id} не найден")
                        return False
                    
                    code = row[0]
                
                # Удаляем код полностью
                return await self.delete_code_completely(code)
                
        except Exception as e:
            logger.error(f"Ошибка при деактивации кода по ID: {e}")
            return False
    
    async def add_user(self, user: UserModel) -> bool:
        """Добавление или обновление пользователя"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('''
                    INSERT OR REPLACE INTO users (user_id, username, first_name, is_subscribed, joined_at)
                    VALUES (?, ?, ?, ?, ?)
                ''', (user.user_id, user.username, user.first_name, user.is_subscribed, user.joined_at))
                
                await db.commit()
                logger.info(f"Пользователь {user.user_id} добавлен/обновлен")
                return True
                
        except Exception as e:
            logger.error(f"Ошибка при добавлении пользователя: {e}")
            return False
    
    async def get_all_subscribers(self) -> List[int]:
        """Получение всех подписчиков"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT user_id FROM users WHERE is_subscribed = 1") as cursor:
                rows = await cursor.fetchall()
                return [row[0] for row in rows]
    
    async def get_user_stats(self) -> Tuple[int, int, List[dict]]:
        """Статистика пользователей: общее количество, подписчики, последние 5"""
        async with aiosqlite.connect(self.db_path) as db:
            # Общее количество пользователей
            async with db.execute("SELECT COUNT(*) FROM users") as cursor:
                total_users = (await cursor.fetchone())[0]
            
            # Количество подписчиков
            async with db.execute("SELECT COUNT(*) FROM users WHERE is_subscribed = 1") as cursor:
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
        """Подписка пользователя"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("UPDATE users SET is_subscribed = 1 WHERE user_id = ?", (user_id,))
                await db.commit()
                logger.info(f"Пользователь {user_id} подписался")
                return True
        except Exception as e:
            logger.error(f"Ошибка подписки: {e}")
            return False
    
    async def unsubscribe_user(self, user_id: int) -> bool:
        """Отписка пользователя"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("UPDATE users SET is_subscribed = 0 WHERE user_id = ?", (user_id,))
                await db.commit()
                logger.info(f"Пользователь {user_id} отписался")
                return True
        except Exception as e:
            logger.error(f"Ошибка отписки: {e}")
            return False
    
    # ФУНКЦИИ для работы с сообщениями кодов с обработкой миграций
    
    async def save_code_message(self, code_id: int, user_id: int, message_id: int, code_value: str = None) -> bool:
        """Сохранение связи между кодом и отправленным сообщением с поддержкой миграции"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Если code_value не передан, получаем его из базы
                if not code_value:
                    async with db.execute("SELECT code FROM codes WHERE id = ?", (code_id,)) as cursor:
                        row = await cursor.fetchone()
                        if row:
                            code_value = row[0]
                        else:
                            logger.warning(f"Код с ID {code_id} не найден")
                            return False
                
                # Пробуем вставить с code_value
                try:
                    await db.execute('''
                        INSERT INTO code_messages (code_id, code_value, user_id, message_id, created_at)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (code_id, code_value, user_id, message_id, datetime.utcnow().isoformat()))
                
                except aiosqlite.OperationalError as e:
                    if "no such column: code_value" in str(e):
                        # Колонка code_value не существует - используем старый формат
                        logger.debug("Используем старую схему для сохранения сообщения")
                        await db.execute('''
                            INSERT INTO code_messages (code_id, user_id, message_id, created_at)
                            VALUES (?, ?, ?, ?)
                        ''', (code_id, user_id, message_id, datetime.utcnow().isoformat()))
                    else:
                        raise
                
                await db.commit()
                logger.debug(f"Сохранена связь: код_id={code_id}, user_id={user_id}, message_id={message_id}")
                return True
                
        except Exception as e:
            logger.error(f"Ошибка сохранения связи сообщения: {e}")
            return False
    
    async def get_code_messages_by_value(self, code_value: str) -> List[CodeMessageModel]:
        """Получение всех сообщений для кода по его значению с обработкой миграции"""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                # Пробуем использовать новую схему с code_value
                async with db.execute('''
                    SELECT id, code_id, user_id, message_id, created_at 
                    FROM code_messages 
                    WHERE code_value = ?
                ''', (code_value,)) as cursor:
                    rows = await cursor.fetchall()
                    
            except aiosqlite.OperationalError as e:
                if "no such column: code_value" in str(e):
                    # Используем старую схему через JOIN
                    logger.debug("Используем старую схему для поиска сообщений")
                    async with db.execute('''
                        SELECT cm.id, cm.code_id, cm.user_id, cm.message_id, cm.created_at 
                        FROM code_messages cm
                        JOIN codes c ON c.id = cm.code_id
                        WHERE c.code = ?
                    ''', (code_value,)) as cursor:
                        rows = await cursor.fetchall()
                else:
                    raise
            
            messages = [CodeMessageModel(
                id=row[0],
                code_id=row[1], 
                user_id=row[2],
                message_id=row[3],
                created_at=datetime.fromisoformat(row[4]) if row[4] else None
            ) for row in rows]
            
            logger.info(f"Найдено {len(messages)} сообщений для кода {code_value}")
            return messages
    
    async def reset_database(self) -> bool:
        """Сброс базы данных (удаление кодов и сообщений, сохранение пользователей)"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Удаляем все связанные сообщения
                await db.execute("DELETE FROM code_messages")
                
                # Удаляем все коды
                await db.execute("DELETE FROM codes")
                
                # Сбрасываем счетчики автоинкремента
                await db.execute("DELETE FROM sqlite_sequence WHERE name IN ('codes', 'code_messages')")
                
                await db.commit()
                logger.info("База данных успешно сброшена (коды и сообщения удалены)")
                return True
                
        except Exception as e:
            logger.error(f"Ошибка при сбросе БД: {e}")
            return False
    
    async def get_database_stats(self) -> dict:
        """Статистика базы данных"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                stats = {}
                
                # Количество пользователей
                async with db.execute("SELECT COUNT(*) FROM users") as cursor:
                    stats['users'] = (await cursor.fetchone())[0]
                
                # Общее количество кодов
                async with db.execute("SELECT COUNT(*) FROM codes") as cursor:
                    stats['codes_total'] = (await cursor.fetchone())[0]
                    stats['codes_active'] = stats['codes_total']  # Все коды активные
                
                # Количество записей сообщений
                async with db.execute("SELECT COUNT(*) FROM code_messages") as cursor:
                    stats['messages'] = (await cursor.fetchone())[0]
                
                # Размер файла БД
                if os.path.exists(self.db_path):
                    size_bytes = os.path.getsize(self.db_path)
                    stats['file_size'] = f"{size_bytes / 1024:.1f} KB"
                else:
                    stats['file_size'] = "0 KB"
                
                return stats
                
        except Exception as e:
            logger.error(f"Ошибка получения статистики БД: {e}")
            return {
                'users': 0,
                'codes_active': 0,
                'messages': 0,
                'file_size': '0 KB'
            }

# Глобальный экземпляр базы данных
db = Database()