"""
Оптимизированные утилиты для работы с датами и временем
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


# Функции для обратной совместимости
def get_moscow_time() -> datetime:
    """Получает текущее московское время (обратная совместимость)"""
    return DateTimeUtils.get_moscow_time()


def parse_expiry_date(date_str: str) -> Optional[datetime]:
    """Парсинг даты истечения (обратная совместимость)"""
    return DateTimeUtils.parse_expiry_date(date_str)


def format_expiry_date(date: datetime) -> str:
    """Форматирует дату истечения (обратная совместимость)"""
    return DateTimeUtils.format_expiry_date(date)


def is_code_expired(expires_date: Optional[datetime]) -> bool:
    """Проверяет истечение кода (обратная совместимость)"""
    return DateTimeUtils.is_code_expired(expires_date)