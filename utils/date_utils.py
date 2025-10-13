"""
Оптимизированные утилиты для работы с датами и временем (ПОЛНАЯ совместимость)
"""
from datetime import datetime, timezone, timedelta
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Московский часовой пояс (UTC+3)
MOSCOW_TZ = timezone(timedelta(hours=3))


class DateTimeUtils:
    """Утилиты для работы с датами и временем"""
    
    @staticmethod
    def get_moscow_time() -> datetime:
        """Получает текущее московское время"""
        return datetime.now(MOSCOW_TZ)
    
    @staticmethod
    def parse_expiry_date(date_str: str) -> Optional[datetime]:
        """
        Парсинг даты истечения из строки
        
        Поддерживаемые форматы:
        - "15.10.2025 23:59" (с временем)
        - "15.10.2025" (без времени, устанавливается 23:59)
        
        Возвращает datetime с московским часовым поясом (UTC+3)
        """
        if not date_str or not date_str.strip():
            return None
        
        try:
            date_str = date_str.strip()
            
            # Пробуем парсинг с временем (ДД.ММ.ГГГГ ЧЧ:ММ)
            if len(date_str.split(' ')) == 2:
                try:
                    naive_dt = datetime.strptime(date_str, '%d.%m.%Y %H:%M')
                    return naive_dt.replace(tzinfo=MOSCOW_TZ)
                except ValueError:
                    pass
            
            # Пробуем парсинг только даты (ДД.ММ.ГГГГ) - устанавливаем время 23:59
            if len(date_str.split('.')) == 3:
                try:
                    naive_dt = datetime.strptime(date_str, '%d.%m.%Y')
                    # Устанавливаем время на 23:59 московского времени
                    moscow_dt = naive_dt.replace(hour=23, minute=59, second=59, tzinfo=MOSCOW_TZ)
                    return moscow_dt
                except ValueError:
                    pass
            
            logger.warning(f"Неподдерживаемый формат даты: {date_str}")
            return None
            
        except Exception as e:
            logger.error(f"Ошибка парсинга даты '{date_str}': {e}")
            return None
    
    @staticmethod
    def format_expiry_date(date: datetime) -> str:
        """
        Форматирует дату истечения для отображения пользователю
        Если дата без часового пояса, добавляет "23:59 МСК"
        """
        if not date:
            return "Не указано"
        
        try:
            if date.tzinfo:
                # Дата с часовым поясом - конвертируем в московское время
                moscow_date = date.astimezone(MOSCOW_TZ)
                return moscow_date.strftime('%d.%m.%Y %H:%M МСК')
            else:
                # Дата без часового пояса - просто форматируем
                return date.strftime('%d.%m.%Y %H:%M МСК')
                
        except Exception as e:
            logger.error(f"Ошибка форматирования даты {date}: {e}")
            return "Ошибка даты"
    
    @staticmethod
    def is_code_expired(expires_date: Optional[datetime]) -> bool:
        """
        Проверяет, истек ли код
        
        Работает с датами как с часовым поясом, так и без него
        """
        if not expires_date:
            return False
        
        try:
            moscow_now = DateTimeUtils.get_moscow_time()
            
            # Если дата без часового пояса, считаем её московской
            if expires_date.tzinfo is None:
                expires_moscow = expires_date.replace(tzinfo=MOSCOW_TZ)
            else:
                expires_moscow = expires_date.astimezone(MOSCOW_TZ)
            
            return moscow_now >= expires_moscow
            
        except Exception as e:
            logger.error(f"Ошибка проверки истечения даты {expires_date}: {e}")
            return False
    
    @staticmethod
    def time_until_expiry(expires_date: Optional[datetime]) -> Optional[timedelta]:
        """
        Возвращает время до истечения кода
        
        Returns:
            timedelta: время до истечения (положительное) или None если код уже истек
        """
        if not expires_date:
            return None
        
        try:
            moscow_now = DateTimeUtils.get_moscow_time()
            
            if expires_date.tzinfo is None:
                expires_moscow = expires_date.replace(tzinfo=MOSCOW_TZ)
            else:
                expires_moscow = expires_date.astimezone(MOSCOW_TZ)
            
            time_left = expires_moscow - moscow_now
            
            return time_left if time_left.total_seconds() > 0 else None
            
        except Exception as e:
            logger.error(f"Ошибка расчета времени до истечения {expires_date}: {e}")
            return None
    
    @staticmethod
    def format_time_left(time_left: timedelta) -> str:
        """
        Форматирует оставшееся время в читаемый формат
        
        Args:
            time_left: время до истечения
            
        Returns:
            str: отформатированная строка типа "2 дня 3 часа"
        """
        if not time_left or time_left.total_seconds() <= 0:
            return "Истек"
        
        days = time_left.days
        hours, remainder = divmod(time_left.seconds, 3600)
        minutes = remainder // 60
        
        parts = []
        
        if days > 0:
            parts.append(f"{days} дн.")
        if hours > 0:
            parts.append(f"{hours} ч.")
        if minutes > 0 and days == 0:  # показываем минуты только если нет дней
            parts.append(f"{minutes} мин.")
        
        if not parts:
            return "менее минуты"
        
        return " ".join(parts)
    
    @staticmethod
    def get_date_examples() -> str:
        """
        Возвращает примеры корректного формата дат для пользователя
        """
        now = DateTimeUtils.get_moscow_time()
        tomorrow = now + timedelta(days=1)
        
        return f"""Примеры корректных форматов:
• {tomorrow.strftime('%d.%m.%Y')} (до 23:59)
• {tomorrow.strftime('%d.%m.%Y 15:30')} (до указанного времени)"""


# Функции для ПОЛНОЙ обратной совместимости (те же имена что в оригинале)
def get_moscow_time() -> datetime:
    """Получить текущее время в Москве"""
    return DateTimeUtils.get_moscow_time()


def parse_expiry_date(date_str: str) -> Optional[datetime]:
    """
    Парсинг даты истечения из строки в московском времени.
    Поддерживаемые форматы:
    - ДД.ММ.ГГГГ ЧЧ:ММ (15.10.2025 23:59)
    - ДД.ММ.ГГГГ (15.10.2025) - автоматически 23:59 МСК
    """
    return DateTimeUtils.parse_expiry_date(date_str)


def format_expiry_date(date: datetime) -> str:
    """Форматирование даты истечения для отображения с указанием МСК"""
    return DateTimeUtils.format_expiry_date(date)


def is_code_expired(expires_date: Optional[datetime]) -> bool:
    """Проверка, истек ли код (сравнение в московском времени)"""
    return DateTimeUtils.is_code_expired(expires_date)


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