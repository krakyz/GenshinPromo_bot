rom datetime import datetime, timezone, timedelta
from typing import Optional

# Московское время UTC+3
MOSCOW_TZ = timezone(timedelta(hours=3))

def get_moscow_time() -> datetime:
    """Получить текущее время в Москве"""
    return datetime.now(MOSCOW_TZ)

def parse_expiry_date(date_str: str) -> Optional[datetime]:
    """
    Парсинг даты истечения из строки в московском времени.
    
    Поддерживаемые форматы:
    - ДД.ММ.ГГГГ ЧЧ:ММ (15.10.2025 23:59)
    - ДД.ММ.ГГГГ (15.10.2025) - автоматически 23:59 МСК
    """
    if not date_str.strip():
        return None
    
    try:
        date_str = date_str.strip()
        
        # С временем: ДД.ММ.ГГГГ ЧЧ:ММ
        if len(date_str.split()) == 2:
            naive_dt = datetime.strptime(date_str, "%d.%m.%Y %H:%M")
            return naive_dt.replace(tzinfo=MOSCOW_TZ)
        
        # Без времени: ДД.ММ.ГГГГ (устанавливаем 23:59 МСК)
        elif len(date_str.split('.')) == 3:
            naive_dt = datetime.strptime(date_str, "%d.%m.%Y")
            moscow_dt = naive_dt.replace(hour=23, minute=59, second=59, tzinfo=MOSCOW_TZ)
            return moscow_dt
        
        return None
    except ValueError:
        return None

def format_expiry_date(date: datetime) -> str:
    """Форматирование даты истечения для отображения с указанием МСК"""
    if date.tzinfo:
        # Конвертируем в московское время если нужно
        moscow_date = date.astimezone(MOSCOW_TZ)
        return moscow_date.strftime('%d.%m.%Y %H:%M МСК')
    else:
        # Если timezone не указан, считаем что это уже московское время
        return date.strftime('%d.%m.%Y %H:%M МСК')

def is_code_expired(expires_date: Optional[datetime]) -> bool:
    """Проверка, истек ли код (сравнение в московском времени)"""
    if not expires_date:
        return False
    
    moscow_now = get_moscow_time()
    
    # Если expires_date без timezone, добавляем московский
    if expires_date.tzinfo is None:
        expires_date = expires_date.replace(tzinfo=MOSCOW_TZ)
    
    return moscow_now >= expires_date

def get_time_until_expiry(expires_date: datetime) -> str:
    """Получить время до истечения кода в московском времени"""
    moscow_now = get_moscow_time()
    
    # Если expires_date без timezone, добавляем московский
    if expires_date.tzinfo is None:
        expires_date = expires_date.replace(tzinfo=MOSCOW_TZ)
    
    if moscow_now >= expires_date:
        return "Истек"
    
    delta = expires_date - moscow_now
    
    if delta.days > 0:
        return f"Истекает через {delta.days} дн."
    elif delta.seconds > 3600:
        hours = delta.seconds // 3600
        return f"Истекает через {hours} ч."
    else:
        minutes = delta.seconds // 60
        return f"Истекает через {minutes} мин."

def datetime_to_moscow_string(dt: Optional[datetime]) -> str:
    """Конвертация datetime в строку с московским временем"""
    if not dt:
        return "Не указано"
    
    if dt.tzinfo:
        moscow_dt = dt.astimezone(MOSCOW_TZ)
    else:
        moscow_dt = dt.replace(tzinfo=MOSCOW_TZ)
    
    return moscow_dt.strftime('%d.%m.%Y %H:%M МСК')

def serialize_moscow_datetime(dt: datetime) -> str:
    """Сериализация datetime для сохранения в БД (в UTC)"""
    if dt.tzinfo:
        # Конвертируем в UTC для хранения
        utc_dt = dt.astimezone(timezone.utc)
        return utc_dt.isoformat()
    else:
        # Считаем что это московское время и конвертируем в UTC
        moscow_dt = dt.replace(tzinfo=MOSCOW_TZ)
        utc_dt = moscow_dt.astimezone(timezone.utc)
        return utc_dt.isoformat()

def deserialize_moscow_datetime(dt_str: str) -> datetime:
    """Десериализация datetime из БД (из UTC в московское время)"""
    if not dt_str:
        return None
    
    try:
        # Парсим как UTC
        if dt_str.endswith('+00:00') or dt_str.endswith('Z'):
            utc_dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        else:
            # Если нет timezone info, считаем UTC
            utc_dt = datetime.fromisoformat(dt_str).replace(tzinfo=timezone.utc)
        
        # Конвертируем в московское время
        return utc_dt.astimezone(MOSCOW_TZ)
    except:
        # Fallback для старых записей без timezone
        return datetime.fromisoformat(dt_str).replace(tzinfo=MOSCOW_TZ)
