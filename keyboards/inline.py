from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from typing import List
from models import CodeModel

def get_code_activation_keyboard(code: str, is_expired: bool = False) -> InlineKeyboardMarkup:
    """Создает клавиатуру с кнопкой активации кода и кнопкой просмотра всех кодов"""
    inline_keyboard = []
    
    if not is_expired:
        # Активная кнопка для активации
        activation_url = f"https://genshin.hoyoverse.com/gift?code={code}"
        inline_keyboard.append([
            InlineKeyboardButton(
                text=f"🎁 Активировать код: {code}",
                url=activation_url
            )
        ])
    else:
        # Неактивная кнопка для истекшего кода
        inline_keyboard.append([
            InlineKeyboardButton(
                text=f"❌ Код истек: {code}",
                callback_data="expired_code"
            )
        ])
    
    # Кнопка просмотра всех кодов
    inline_keyboard.append([
        InlineKeyboardButton(text="📋 Все коды", callback_data="view_all_codes")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)

def get_all_codes_keyboard(codes: List[CodeModel]) -> InlineKeyboardMarkup:
    """Создает клавиатуру со всеми кодами для активации"""
    inline_keyboard = []
    
    # Добавляем кнопки для каждого кода (по 1 в ряду для лучшей читаемости)
    for code in codes:
        if code.is_active:
            activation_url = f"https://genshin.hoyoverse.com/gift?code={code.code}"
            inline_keyboard.append([
                InlineKeyboardButton(
                    text=f"🎁 {code.code}",
                    url=activation_url
                )
            ])
    
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)

def get_subscription_keyboard(is_subscribed: bool = False) -> InlineKeyboardMarkup:
    """Создает клавиатуру для управления подпиской (динамическую)"""
    inline_keyboard = []
    
    # Показываем кнопку подписки только если пользователь не подписан
    if not is_subscribed:
        inline_keyboard.append([
            InlineKeyboardButton(text="🔔 Подписаться", callback_data="subscribe")
        ])
    
    # Кнопка просмотра кодов всегда доступна
    inline_keyboard.append([
        InlineKeyboardButton(text="📋 Все коды", callback_data="view_all_codes")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)

def get_admin_keyboard() -> InlineKeyboardMarkup:
    """Создает главную клавиатуру для админа"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ Добавить код", callback_data="admin_add_code"),
            InlineKeyboardButton(text="❌ Деактивировать код", callback_data="admin_expire_code")
        ],
        [
            InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"),
            InlineKeyboardButton(text="📋 Активные коды", callback_data="admin_active_codes")
        ],
        [
            InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users"),
            InlineKeyboardButton(text="📢 Реклама", callback_data="admin_custom_post")
        ],
        [
            InlineKeyboardButton(text="🗄️ База данных", callback_data="admin_database")
        ]
    ])
    
    return keyboard

def get_admin_stats_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру для страницы статистики"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_stats")
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")
        ]
    ])
    
    return keyboard

def get_admin_codes_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру для страницы активных кодов"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_active_codes")
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")
        ]
    ])
    
    return keyboard

def get_admin_users_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру для страницы пользователей"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_users")
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")
        ]
    ])
    
    return keyboard

def get_codes_navigation_keyboard() -> InlineKeyboardMarkup:
    """Создает минимальную клавиатуру для навигации (только просмотр кодов)"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📋 Все коды", callback_data="view_all_codes")
        ]
    ])
    
    return keyboard

def get_database_admin_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру для управления базой данных"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📥 Скачать БД", callback_data="admin_download_db"),
            InlineKeyboardButton(text="🗑️ Сбросить БД", callback_data="admin_reset_db")
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")
        ]
    ])
    
    return keyboard

def get_custom_post_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру для кастомного поста (только просмотр кодов)"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📋 Все коды", callback_data="view_all_codes")
        ]
    ])
    
    return keyboard

def get_custom_post_with_button_keyboard(button_text: str, button_url: str) -> InlineKeyboardMarkup:
    """Создает клавиатуру для кастомного поста с дополнительной кнопкой"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=button_text, url=button_url)
        ],
        [
            InlineKeyboardButton(text="📋 Все коды", callback_data="view_all_codes")
        ]
    ])
    
    return keyboard