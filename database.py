import sqlite3
import logging
from datetime import datetime
from typing import List, Optional, Tuple
from dataclasses import dataclass
import json

@dataclass
class User:
    user_id: int
    username: Optional[str]
    first_name: Optional[str]
    is_subscribed: bool
    created_at: datetime

@dataclass 
class PromoCode:
    id: Optional[int]
    code: str
    description: str
    expiry_date: Optional[datetime]
    is_active: bool
    created_at: datetime
    sent_count: int = 0

@dataclass
class SentMessage:
    id: Optional[int]
    user_id: int
    promo_code_id: int
    message_id: int
    chat_id: int
    sent_at: datetime

class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Инициализация базы данных"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    is_subscribed BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS promo_codes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE NOT NULL,
                    description TEXT NOT NULL,
                    expiry_date TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    sent_count INTEGER DEFAULT 0
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS sent_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    promo_code_id INTEGER,
                    message_id INTEGER,
                    chat_id INTEGER,
                    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id),
                    FOREIGN KEY (promo_code_id) REFERENCES promo_codes (id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS advertisements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    image_url TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    sent_count INTEGER DEFAULT 0
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sent_messages_promo_code 
                ON sent_messages(promo_code_id)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_users_subscribed 
                ON users(is_subscribed) WHERE is_subscribed = TRUE
            """)

            conn.commit()
            logging.info("База данных инициализирована")

    def add_user(self, user_id: int, username: Optional[str] = None, 
                 first_name: Optional[str] = None) -> User:
        """Добавление пользователя"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO users (user_id, username, first_name, is_subscribed)
                VALUES (?, ?, ?, COALESCE((SELECT is_subscribed FROM users WHERE user_id = ?), TRUE))
            """, (user_id, username, first_name, user_id))
            conn.commit()

            cursor = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            row = cursor.fetchone()
            return User(
                user_id=row[0],
                username=row[1], 
                first_name=row[2],
                is_subscribed=bool(row[3]),
                created_at=datetime.fromisoformat(row[4])
            )

    def get_user(self, user_id: int) -> Optional[User]:
        """Получение пользователя"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            row = cursor.fetchone()
            if row:
                return User(
                    user_id=row[0],
                    username=row[1],
                    first_name=row[2], 
                    is_subscribed=bool(row[3]),
                    created_at=datetime.fromisoformat(row[4])
                )
            return None

    def subscribe_user(self, user_id: int) -> bool:
        """Подписка пользователя"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('SELECT is_subscribed FROM users WHERE user_id = ?', (user_id,))
            row = cursor.fetchone()

            if row and row[0]:
                return False  # Уже подписан

            conn.execute('UPDATE users SET is_subscribed = TRUE WHERE user_id = ?', (user_id,))
            conn.commit()
            return True

    def unsubscribe_user(self, user_id: int) -> bool:
        """Отписка пользователя"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('SELECT is_subscribed FROM users WHERE user_id = ?', (user_id,))
            row = cursor.fetchone()

            if not row or not row[0]:
                return False  # Не подписан

            conn.execute('UPDATE users SET is_subscribed = FALSE WHERE user_id = ?', (user_id,))
            conn.commit()
            return True

    def get_subscribed_users(self) -> List[User]:
        """Получение всех подписанных пользователей"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('SELECT * FROM users WHERE is_subscribed = TRUE')
            users = []
            for row in cursor.fetchall():
                users.append(User(
                    user_id=row[0],
                    username=row[1],
                    first_name=row[2],
                    is_subscribed=bool(row[3]),
                    created_at=datetime.fromisoformat(row[4])
                ))
            return users

    def add_promo_code(self, code: str, description: str, 
                      expiry_date: Optional[datetime] = None) -> Optional[PromoCode]:
        """Добавление промокода"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    INSERT INTO promo_codes (code, description, expiry_date)
                    VALUES (?, ?, ?)
                """, (code, description, expiry_date.isoformat() if expiry_date else None))

                promo_id = cursor.lastrowid
                conn.commit()

                return PromoCode(
                    id=promo_id,
                    code=code,
                    description=description,
                    expiry_date=expiry_date,
                    is_active=True,
                    created_at=datetime.now()
                )
        except sqlite3.IntegrityError:
            return None  # Код уже существует

    def get_promo_code(self, code_id: int) -> Optional[PromoCode]:
        """Получение промокода по ID"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('SELECT * FROM promo_codes WHERE id = ?', (code_id,))
            row = cursor.fetchone()
            if row:
                return PromoCode(
                    id=row[0],
                    code=row[1],
                    description=row[2],
                    expiry_date=datetime.fromisoformat(row[3]) if row[3] else None,
                    is_active=bool(row[4]),
                    created_at=datetime.fromisoformat(row[5]),
                    sent_count=row[6]
                )
            return None

    def get_active_promo_codes(self) -> List[PromoCode]:
        """Получение активных промокодов"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('SELECT * FROM promo_codes WHERE is_active = TRUE ORDER BY created_at DESC')
            codes = []
            for row in cursor.fetchall():
                codes.append(PromoCode(
                    id=row[0],
                    code=row[1],
                    description=row[2],
                    expiry_date=datetime.fromisoformat(row[3]) if row[3] else None,
                    is_active=bool(row[4]),
                    created_at=datetime.fromisoformat(row[5]),
                    sent_count=row[6]
                ))
            return codes

    def deactivate_promo_code(self, code_id: int) -> bool:
        """Деактивация промокода"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('UPDATE promo_codes SET is_active = FALSE WHERE id = ?', (code_id,))
            conn.commit()
            return cursor.rowcount > 0

    def add_sent_message(self, user_id: int, promo_code_id: int, 
                        message_id: int, chat_id: int) -> SentMessage:
        """Сохранение отправленного сообщения"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                INSERT INTO sent_messages (user_id, promo_code_id, message_id, chat_id)
                VALUES (?, ?, ?, ?)
            """, (user_id, promo_code_id, message_id, chat_id))

            sent_id = cursor.lastrowid
            conn.commit()

            # Обновляем счетчик отправленных сообщений для промокода
            conn.execute("""
                UPDATE promo_codes SET sent_count = sent_count + 1 WHERE id = ?
            """, (promo_code_id,))
            conn.commit()

            return SentMessage(
                id=sent_id,
                user_id=user_id,
                promo_code_id=promo_code_id,
                message_id=message_id,
                chat_id=chat_id,
                sent_at=datetime.now()
            )

    def get_sent_messages_by_promo(self, promo_code_id: int) -> List[SentMessage]:
        """Получение всех отправленных сообщений для промокода"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT * FROM sent_messages WHERE promo_code_id = ?
            """, (promo_code_id,))

            messages = []
            for row in cursor.fetchall():
                messages.append(SentMessage(
                    id=row[0],
                    user_id=row[1],
                    promo_code_id=row[2],
                    message_id=row[3],
                    chat_id=row[4],
                    sent_at=datetime.fromisoformat(row[5])
                ))
            return messages

    def get_statistics(self) -> dict:
        """Получение статистики бота"""
        with sqlite3.connect(self.db_path) as conn:
            stats = {}

            # Общее количество пользователей
            cursor = conn.execute('SELECT COUNT(*) FROM users')
            stats['total_users'] = cursor.fetchone()[0]

            # Подписанные пользователи  
            cursor = conn.execute('SELECT COUNT(*) FROM users WHERE is_subscribed = TRUE')
            stats['subscribed_users'] = cursor.fetchone()[0]

            # Активные промокоды
            cursor = conn.execute('SELECT COUNT(*) FROM promo_codes WHERE is_active = TRUE')
            stats['active_codes'] = cursor.fetchone()[0]

            # Всего промокодов
            cursor = conn.execute('SELECT COUNT(*) FROM promo_codes')
            stats['total_codes'] = cursor.fetchone()[0]

            # Отправленные сообщения
            cursor = conn.execute('SELECT COUNT(*) FROM sent_messages')
            stats['sent_messages'] = cursor.fetchone()[0]

            # Последние пользователи
            cursor = conn.execute("""
                SELECT user_id, first_name, created_at 
                FROM users 
                ORDER BY created_at DESC 
                LIMIT 5
            """)
            stats['recent_users'] = cursor.fetchall()

            return stats

    def reset_database(self) -> bool:
        """Сброс базы данных (только для админов)"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('DELETE FROM sent_messages')
                conn.execute('DELETE FROM promo_codes') 
                conn.execute('DELETE FROM users')
                conn.execute('DELETE FROM advertisements')
                conn.commit()
                return True
        except Exception as e:
            logging.error(f"Ошибка при сбросе БД: {e}")
            return False