from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class CodeModel:
    """Модель для промо-кода Genshin Impact"""
    id: Optional[int] = None
    code: str = ""
    description: str = ""
    rewards: str = ""
    is_active: bool = True
    created_at: Optional[datetime] = None
    expired_at: Optional[datetime] = None
    expires_date: Optional[datetime] = None  # Планируемая дата истечения
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()

@dataclass
class UserModel:
    """Модель для пользователя"""
    id: Optional[int] = None
    user_id: int = 0
    username: Optional[str] = None
    first_name: Optional[str] = None
    is_subscribed: bool = True
    joined_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.joined_at is None:
            self.joined_at = datetime.now()

@dataclass
class CustomPostModel:
    """Модель для кастомного рекламного поста"""
    id: Optional[int] = None
    title: str = ""
    text: str = ""
    image_path: Optional[str] = None
    button_text: Optional[str] = None
    button_url: Optional[str] = None
    created_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()

@dataclass
class CodeMessageModel:
    """Модель для отслеживания отправленных сообщений с кодами"""
    id: Optional[int] = None
    code_id: int = 0
    user_id: int = 0
    message_id: int = 0
    created_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()