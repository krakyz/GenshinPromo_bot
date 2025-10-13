"""
Оптимизированные модели данных с обратной совместимостью
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any


@dataclass
class UserModel:
    """Модель пользователя с дополнительными свойствами"""
    user_id: int
    id: Optional[int] = None
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    language_code: Optional[str] = 'ru'
    is_subscribed: bool = True
    joined_at: Optional[datetime] = None
    last_activity: Optional[datetime] = None
    
    def __post_init__(self):
        """Постобработка после инициализации"""
        # Устанавливаем время по умолчанию
        if self.joined_at is None:
            self.joined_at = datetime.now()
        if self.last_activity is None:
            self.last_activity = datetime.now()
            
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


@dataclass
class CodeModel:
    """Модель промо-кода с расширенными возможностями"""
    code: str = ""
    description: str = ""
    rewards: str = ""
    id: Optional[int] = None
    expires_date: Optional[datetime] = None  # Планируемая дата истечения
    created_at: Optional[datetime] = None
    expired_at: Optional[datetime] = None  # Фактическая дата истечения
    is_active: bool = True
    usage_count: int = 0
    max_uses: Optional[int] = None
    
    def __post_init__(self):
        """Постобработка после инициализации"""
        # Устанавливаем время создания
        if self.created_at is None:
            self.created_at = datetime.now()
            
        # Приводим код к верхнему регистру
        if self.code:
            self.code = self.code.upper().strip()
        
        # Обрезаем длинные строки
        if self.description and len(self.description) > 500:
            self.description = self.description[:500]
        if self.rewards and len(self.rewards) > 500:
            self.rewards = self.rewards[:500]
        
        # Базовая валидация кода
        if self.code and (len(self.code) < 3 or len(self.code) > 20):
            raise ValueError(f"Неверная длина кода: {self.code}")
    
    @property
    def is_expired(self) -> bool:
        """Проверяет, истек ли код"""
        if not self.expires_date:
            return False
        
        try:
            from utils.date_utils import DateTimeUtils
            return DateTimeUtils.is_code_expired(self.expires_date)
        except ImportError:
            # Fallback для обратной совместимости
            return datetime.now() >= self.expires_date
    
    @property
    def formatted_expiry(self) -> str:
        """Возвращает отформатированную дату истечения"""
        if not self.expires_date:
            return "Не указано"
        
        try:
            from utils.date_utils import DateTimeUtils
            return DateTimeUtils.format_expiry_date(self.expires_date)
        except ImportError:
            # Fallback для обратной совместимости
            return self.expires_date.strftime('%d.%m.%Y %H:%M МСК')
    
    @property
    def activation_url(self) -> str:
        """Возвращает URL для активации кода"""
        return f"https://genshin.hoyoverse.com/gift?code={self.code}"


@dataclass 
class CodeMessageModel:
    """Модель для отслеживания отправленных сообщений с кодами (обратная совместимость)"""
    code_id: int = 0
    user_id: int = 0
    message_id: int = 0
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    is_active: bool = True
    
    def __post_init__(self):
        """Постобработка после инициализации"""
        if self.created_at is None:
            self.created_at = datetime.now()


# Новая модель (алиас для совместимости)
@dataclass
class MessageModel(CodeMessageModel):
    """Улучшенная модель сообщения (наследует CodeMessageModel для совместимости)"""
    pass


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