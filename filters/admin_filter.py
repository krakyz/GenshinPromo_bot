from aiogram.filters import Filter
from aiogram.types import Message
from config import ADMIN_IDS

class AdminFilter(Filter):
    """Фильтр для проверки, является ли пользователь администратором"""
    
    async def __call__(self, message: Message) -> bool:
        return message.from_user.id in ADMIN_IDS