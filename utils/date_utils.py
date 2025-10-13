from datetime import datetime, timedelta
from typing import Optional

def parse_expiry_date(date_str: str) -> Optional[datetime]:
    """
    Парсинг даты истечения из строки.
    
    Поддерживаемые форматы:
    - ДД.ММ.ГГГГ ЧЧ:ММ (15.10.2025 23:59)
    - ДД.ММ.ГГГГ (15.10.2025) - автоматически 23:59
    """
    if not date_str.strip():
        return None
    
    try:
        date_str = date_str.strip()
        
        # С временем: ДД.ММ.ГГГГ ЧЧ:ММ
        if len(date_str.split()) == 2:
            return datetime.strptime(date_str, "%d.%m.%Y %H:%M")
        
        # Без времени: ДД.ММ.ГГГГ (устанавливаем 23:59)
        elif len(date_str.split('.')) == 3:
            date_part = datetime.strptime(date_str, "%d.%m.%Y")
            return date_part.replace(hour=23, minute=59, second=59)
        
        return None
    except ValueError:
        return None

def format_expiry_date(date: datetime) -> str:
    """Форматирование даты истечения для отображения"""
    return date.strftime('%d.%m.%Y %H:%M')

def is_code_expired(expires_date: Optional[datetime]) -> bool:
    """Проверка, истек ли код"""
    if not expires_date:
        return False
    return datetime.now() >= expires_date

def get_time_until_expiry(expires_date: datetime) -> str:
    """Получить время до истечения кода"""
    now = datetime.now()
    if now >= expires_date:
        return "Истек"
    
    delta = expires_date - now
    
    if delta.days > 0:
        return f"Истекает через {delta.days} дн."
    elif delta.seconds > 3600:
        hours = delta.seconds // 3600
        return f"Истекает через {hours} ч."
    else:
        minutes = delta.seconds // 60
        return f"Истекает через {minutes} мин."