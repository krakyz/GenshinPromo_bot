import aiosqlite
import logging
from typing import List, Optional, Tuple
from datetime import datetime
from models import CodeModel, UserModel, CustomPostModel
from config import DATABASE_PATH
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
                    expired_at TIMESTAMP
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
            
            # Таблица для кастомных постов
            await db.execute('''
                CREATE TABLE IF NOT EXISTS custom_posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    text TEXT NOT NULL,
                    image_path TEXT,
                    button_text TEXT,
                    button_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await db.commit()
            logger.info("База данных инициализирована")
    
    async def add_code(self, code: CodeModel) -> bool:
        """Добавить новый промо-код"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('''
                    INSERT INTO codes (code, description, rewards, is_active, created_at, expired_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    code.code,
                    code.description,
                    code.rewards,
                    code.is_active,
                    code.created_at,
                    code.expired_at
                ))
                await db.commit()
                logger.info(f"Добавлен новый код: {code.code}")
                return True
        except aiosqlite.IntegrityError:
            logger.warning(f"Код {code.code} уже существует")
            return False
        except Exception as e:
            logger.error(f"Ошибка при добавлении кода: {e}")
            return False
    
    async def get_active_codes(self) -> List[CodeModel]:
        """Получить все активные промо-коды"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute('''
                SELECT id, code, description, rewards, is_active, created_at, expired_at
                FROM codes
                WHERE is_active = 1
                ORDER BY created_at DESC
            ''') as cursor:
                rows = await cursor.fetchall()
                return [
                    CodeModel(
                        id=row[0],
                        code=row[1],
                        description=row[2],
                        rewards=row[3],
                        is_active=bool(row[4]),
                        created_at=datetime.fromisoformat(row[5]) if row[5] else None,
                        expired_at=datetime.fromisoformat(row[6]) if row[6] else None
                    )
                    for row in rows
                ]
    
    async def expire_code(self, code: str) -> bool:
        """Пометить код как истекший"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute('''
                    UPDATE codes SET is_active = 0, expired_at = ?
                    WHERE code = ? AND is_active = 1
                ''', (datetime.now(), code))
                await db.commit()
                
                if cursor.rowcount > 0:
                    logger.info(f"Код {code} помечен как истекший")
                    return True
                else:
                    logger.warning(f"Активный код {code} не найден")
                    return False
        except Exception as e:
            logger.error(f"Ошибка при истечении кода: {e}")
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
    
    async def unsubscribe_user(self, user_id: int) -> bool:
        """Отписать пользователя от рассылки"""
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
    
    async def add_custom_post(self, post: CustomPostModel) -> bool:
        """Добавить кастомный пост для рассылки"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('''
                    INSERT INTO custom_posts (title, text, image_path, button_text, button_url, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    post.title,
                    post.text,
                    post.image_path,
                    post.button_text,
                    post.button_url,
                    post.created_at
                ))
                await db.commit()
                logger.info(f"Добавлен кастомный пост: {post.title}")
                return True
        except Exception as e:
            logger.error(f"Ошибка при добавлении кастомного поста: {e}")
            return False
    
    async def save_image(self, file_path: str, file_id: str) -> bool:
        """Сохранить путь к изображению"""
        try:
            # Создаем папку для изображений если её нет
            images_dir = "images"
            if not os.path.exists(images_dir):
                os.makedirs(images_dir)
            
            # Сохраняем информацию о файле в базе данных или файле
            # В реальном проекте здесь можно сохранить file_id для повторного использования
            logger.info(f"Изображение сохранено: {file_path}, file_id: {file_id}")
            return True
        except Exception as e:
            logger.error(f"Ошибка при сохранении изображения: {e}")
            return False

# Создаем глобальный экземпляр базы данных
db = Database()