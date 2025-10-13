"""
Оптимизированные модели данных с расширенной функциональностью
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
import json


@dataclass
class UserModel:
    """Модель пользователя с дополнительными свойствами"""
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    language_code: Optional[str] = 'ru'
    is_subscribed: bool = True
    joined_at: Optional[datetime] = field(default_factory=datetime.now)
    last_activity: Optional[datetime] = field(default_factory=datetime.now)
    
    def __post_init__(self):
        """Постобработка после инициализации"""
        # Обрезаем длинные имена
        if self.first_name and len(self.first_name) > 64:
            self.first_name = self.first_name[:64]
        if self.last_name and len(self.last_name) > 64:
            self.last_name = self.last_name[:64]
        if self.username and len(self.username) > 32:
            self.username = self.username[:32]
    
    @property
    def display_name(self) -> str:
        """Возвращает имя для отображения"""
        if self.first_name:
            return self.first_name
        elif self.username:
            return f"@{self.username}"
        else:
            return f"User {self.user_id}"
    
    @property
    def full_name(self) -> str:
        """Возвращает полное имя"""
        parts = []
        if self.first_name:
            parts.append(self.first_name)
        if self.last_name:
            parts.append(self.last_name)
        
        return " ".join(parts) if parts else self.display_name
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразует модель в словарь"""
        return {
            'user_id': self.user_id,
            'username': self.username,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'language_code': self.language_code,
            'is_subscribed': self.is_subscribed,
            'joined_at': self.joined_at.isoformat() if self.joined_at else None,
            'last_activity': self.last_activity.isoformat() if self.last_activity else None
        }


@dataclass
class CodeModel:
    """Модель промо-кода с расширенными возможностями"""
    code: str
    description: Optional[str] = None
    rewards: Optional[str] = None
    expires_date: Optional[datetime] = None
    created_at: Optional[datetime] = field(default_factory=datetime.now)
    is_active: bool = True
    id: Optional[int] = None
    usage_count: int = 0
    max_uses: Optional[int] = None
    
    def __post_init__(self):
        """Постобработка после инициализации"""
        # Приводим код к верхнему регистру
        self.code = self.code.upper().strip()
        
        # Обрезаем длинные строки
        if self.description and len(self.description) > 500:
            self.description = self.description[:500]
        if self.rewards and len(self.rewards) > 500:
            self.rewards = self.rewards[:500]
        
        # Валидация кода
        if not self.code or len(self.code) < 3:
            raise ValueError("Код должен содержать минимум 3 символа")
        
        if len(self.code) > 20:
            raise ValueError("Код не может быть длиннее 20 символов")
    
    @property
    def is_expired(self) -> bool:
        """Проверяет, истек ли код"""
        if not self.expires_date:
            return False
        
        from utils.date_utils import DateTimeUtils
        return DateTimeUtils.is_code_expired(self.expires_date)
    
    @property
    def time_left(self):
        """Возвращает оставшееся время до истечения"""
        if not self.expires_date:
            return None
        
        from utils.date_utils import DateTimeUtils
        return DateTimeUtils.time_until_expiry(self.expires_date)
    
    @property
    def formatted_expiry(self) -> str:
        """Возвращает отформатированную дату истечения"""
        if not self.expires_date:
            return "Не указано"
        
        from utils.date_utils import DateTimeUtils
        return DateTimeUtils.format_expiry_date(self.expires_date)
    
    @property
    def activation_url(self) -> str:
        """Возвращает URL для активации кода"""
        return f"https://genshin.hoyoverse.com/gift?code={self.code}"
    
    def is_usage_limited(self) -> bool:
        """Проверяет, ограничено ли использование кода"""
        return self.max_uses is not None and self.usage_count >= self.max_uses
    
    def can_be_used(self) -> bool:
        """Проверяет, можно ли использовать код"""
        return (
            self.is_active and
            not self.is_expired and
            not self.is_usage_limited()
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразует модель в словарь"""
        return {
            'id': self.id,
            'code': self.code,
            'description': self.description,
            'rewards': self.rewards,
            'expires_date': self.expires_date.isoformat() if self.expires_date else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'is_active': self.is_active,
            'usage_count': self.usage_count,
            'max_uses': self.max_uses,
            'is_expired': self.is_expired,
            'activation_url': self.activation_url
        }
    
    def to_user_text(self) -> str:
        """Возвращает текст для отображения пользователю"""
        text = f"🔥 **{self.code}**\n"
        
        if self.description:
            text += f"📝 {self.description}\n"
        
        if self.rewards:
            text += f"💎 {self.rewards}\n"
        
        if self.expires_date:
            text += f"⏰ До: {self.formatted_expiry}\n"
        
        return text


@dataclass
class MessageModel:
    """Модель сообщения с кодом"""
    id: Optional[int] = None
    code_id: int = None
    user_id: int = None
    message_id: int = None
    created_at: Optional[datetime] = field(default_factory=datetime.now)
    is_active: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразует модель в словарь"""
        return {
            'id': self.id,
            'code_id': self.code_id,
            'user_id': self.user_id,
            'message_id': self.message_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'is_active': self.is_active
        }


@dataclass
class BroadcastStats:
    """Статистика рассылки"""
    total_users: int = 0
    sent_count: int = 0
    failed_count: int = 0
    blocked_count: int = 0
    start_time: Optional[datetime] = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    
    @property
    def success_rate(self) -> float:
        """Процент успешной доставки"""
        if self.total_users == 0:
            return 0.0
        return (self.sent_count / self.total_users) * 100
    
    @property
    def duration(self) -> Optional[float]:
        """Длительность рассылки в секундах"""
        if not self.end_time or not self.start_time:
            return None
        return (self.end_time - self.start_time).total_seconds()
    
    def finish(self):
        """Завершает подсчет времени рассылки"""
        self.end_time = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразует статистику в словарь"""
        return {
            'total_users': self.total_users,
            'sent_count': self.sent_count,
            'failed_count': self.failed_count,
            'blocked_count': self.blocked_count,
            'success_rate': self.success_rate,
            'duration': self.duration,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None
        }
    
    def to_report_text(self) -> str:
        """Генерирует текст отчета"""
        text = f"""📊 **Статистика рассылки**

👥 Всего пользователей: {self.total_users}
✅ Отправлено: {self.sent_count}
❌ Ошибок: {self.failed_count}
🚫 Заблокировано: {self.blocked_count}

📈 Успешность: {self.success_rate:.1f}%"""

        if self.duration:
            text += f"\n⏱️ Время: {self.duration:.1f} сек"

        return text


# Константы для валидации
class ModelConstants:
    """Константы для валидации моделей"""
    
    # Пользователь
    MAX_USERNAME_LENGTH = 32
    MAX_NAME_LENGTH = 64
    
    # Промо-код
    MIN_CODE_LENGTH = 3
    MAX_CODE_LENGTH = 20
    MAX_DESCRIPTION_LENGTH = 500
    MAX_REWARDS_LENGTH = 500
    
    # Общие
    MAX_MESSAGE_LENGTH = 4096  # Лимит Telegram для сообщений


# Утилитарные функции
def validate_code_format(code: str) -> bool:
    """Проверяет формат промо-кода"""
    if not code:
        return False
    
    code = code.strip().upper()
    
    # Длина
    if len(code) < ModelConstants.MIN_CODE_LENGTH or len(code) > ModelConstants.MAX_CODE_LENGTH:
        return False
    
    # Только буквы и цифры
    if not code.isalnum():
        return False
    
    return True


def sanitize_text(text: Optional[str], max_length: int = 500) -> Optional[str]:
    """Очищает и обрезает текст"""
    if not text:
        return None
    
    # Удаляем лишние пробелы
    text = " ".join(text.split())
    
    # Обрезаем до максимальной длины
    if len(text) > max_length:
        text = text[:max_length].rstrip()
    
    return text if text else None