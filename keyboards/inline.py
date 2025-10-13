"""
Оптимизированные клавиатуры с таймерами валидации и функциями истекших кодов
"""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from typing import List, Tuple, Optional
from models import CodeModel


class KeyboardBuilder:
    """Универсальный строитель клавиатур"""
    
    @staticmethod
    def create_keyboard(
        buttons: List[List[Tuple[str, str]]],
        back_button: bool = False,
        refresh_button: Optional[str] = None
    ) -> InlineKeyboardMarkup:
        """
        Создает клавиатуру из списка кнопок
        
        Args:
            buttons: List[List[Tuple[text, callback_data]]]
            back_button: добавить кнопку "Назад"
            refresh_button: callback_data для кнопки обновления
        """
        keyboard = []
        
        for row in buttons:
            keyboard_row = []
            for text, callback_data in row:
                keyboard_row.append(InlineKeyboardButton(text=text, callback_data=callback_data))
            keyboard.append(keyboard_row)
        
        # Добавляем кнопку обновления если указана
        if refresh_button:
            keyboard.append([InlineKeyboardButton(text="🔄 Обновить", callback_data=refresh_button)])
        
        # Добавляем кнопку "Назад" если нужна
        if back_button:
            keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")])
        
        return InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    @staticmethod
    def create_url_keyboard(
        buttons: List[Tuple[str, str]],
        additional_buttons: Optional[List[List[Tuple[str, str]]]] = None
    ) -> InlineKeyboardMarkup:
        """Создает клавиатуру с URL кнопками"""
        keyboard = []
        
        for text, url in buttons:
            keyboard.append([InlineKeyboardButton(text=text, url=url)])
        
        if additional_buttons:
            for row in additional_buttons:
                keyboard_row = []
                for text, callback_data in row:
                    keyboard_row.append(InlineKeyboardButton(text=text, callback_data=callback_data))
                keyboard.append(keyboard_row)
        
        return InlineKeyboardMarkup(inline_keyboard=keyboard)


# Фабрики специализированных клавиатур
def get_code_activation_keyboard(code: str, is_expired: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура для активации промо-кода или отображения истекшего"""
    if is_expired:
        return KeyboardBuilder.create_keyboard(
            buttons=[[(f"❌ Код истек: {code}", "expired_code")]],
            additional_buttons=[[("📋 Все коды", "view_all_codes")]]
        )
    
    activation_url = f"https://genshin.hoyoverse.com/gift?code={code}"
    return KeyboardBuilder.create_url_keyboard(
        buttons=[(f"🎁 Активировать код: {code}", activation_url)],
        additional_buttons=[[("📋 Все коды", "view_all_codes")]]
    )


def get_all_codes_keyboard(codes: List[CodeModel]) -> InlineKeyboardMarkup:
    """Клавиатура со всеми активными кодами"""
    url_buttons = []
    for code in codes:
        if code.is_active:
            activation_url = f"https://genshin.hoyoverse.com/gift?code={code.code}"
            url_buttons.append((f"🎁 {code.code}", activation_url))
    
    return KeyboardBuilder.create_url_keyboard(buttons=url_buttons)


def get_subscription_keyboard(is_subscribed: bool = False) -> InlineKeyboardMarkup:
    """Динамическая клавиатура подписки"""
    buttons = []
    
    if not is_subscribed:
        buttons.append([("🔔 Подписаться", "subscribe")])
    
    buttons.append([("📋 Все коды", "view_all_codes")])
    
    return KeyboardBuilder.create_keyboard(buttons=buttons)


# Админские клавиатуры
def get_admin_keyboard() -> InlineKeyboardMarkup:
    """Главное меню админ-панели"""
    return KeyboardBuilder.create_keyboard(buttons=[
        [("➕ Добавить код", "admin_add_code"), ("❌ Деактивировать код", "admin_expire_code")],
        [("📊 Статистика", "admin_stats"), ("📋 Активные коды", "admin_active_codes")],
        [("👥 Пользователи", "admin_users"), ("📢 Реклама", "admin_custom_post")],
        [("🗄️ База данных", "admin_database")]
    ])


def get_admin_stats_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура страницы статистики (БЕЗ списка кодов)"""
    return KeyboardBuilder.create_keyboard(
        buttons=[],
        back_button=True,
        refresh_button="admin_stats"
    )


def get_admin_codes_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура страницы активных кодов"""
    return KeyboardBuilder.create_keyboard(
        buttons=[],
        back_button=True,
        refresh_button="admin_active_codes"
    )


def get_admin_users_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура страницы пользователей"""
    return KeyboardBuilder.create_keyboard(
        buttons=[],
        back_button=True,
        refresh_button="admin_users"
    )


def get_database_admin_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура управления базой данных"""
    return KeyboardBuilder.create_keyboard(
        buttons=[
            [("📥 Скачать БД", "admin_download_db"), ("🗑️ Сбросить БД", "admin_reset_db")]
        ],
        back_button=True
    )


def get_admin_back_keyboard() -> InlineKeyboardMarkup:
    """Простая клавиатура только с кнопкой "Назад" """
    return KeyboardBuilder.create_keyboard(buttons=[], back_button=True)


# Новые клавиатуры для деактивации кодов с таймером
def get_admin_expire_codes_keyboard(codes: List[CodeModel]) -> InlineKeyboardMarkup:
    """Клавиатура с кнопками кодов для деактивации"""
    buttons = []
    
    for code in codes:
        buttons.append([(f"🔥 {code.code}", f"expire_code_{code.code}")])
    
    return KeyboardBuilder.create_keyboard(buttons=buttons, back_button=True)


def get_expire_code_timer_keyboard(code: str, seconds_left: int) -> InlineKeyboardMarkup:
    """Клавиатура с таймером для подтверждения деактивации"""
    if seconds_left > 0:
        button_text = f"⏳ Подтверждение через {seconds_left} сек"
        callback_data = f"timer_{code}_{seconds_left-1}"
    else:
        button_text = f"❌ ДЕАКТИВИРОВАТЬ {code}"
        callback_data = f"confirm_expire_{code}"
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=button_text, callback_data=callback_data)],
        [InlineKeyboardButton(text="🔙 Отмена", callback_data="admin_expire_code")]
    ])


# Новые клавиатуры для сброса БД с таймером
def get_reset_db_timer_keyboard(seconds_left: int) -> InlineKeyboardMarkup:
    """Клавиатура с таймером для подтверждения сброса БД"""
    if seconds_left > 0:
        button_text = f"⏳ Подтверждение через {seconds_left} сек"
        callback_data = f"reset_timer_{seconds_left-1}"
    else:
        button_text = "🗑️ СБРОСИТЬ БАЗУ ДАННЫХ"
        callback_data = "confirm_reset_db"
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=button_text, callback_data=callback_data)],
        [InlineKeyboardButton(text="🔙 Отмена", callback_data="admin_database")]
    ])


# Алиасы для обратной совместимости
get_admin_add_code_keyboard = get_admin_back_keyboard
get_admin_expire_code_keyboard = get_admin_back_keyboard
get_admin_custom_post_keyboard = get_admin_back_keyboard


def get_custom_post_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для кастомного поста (только просмотр кодов)"""
    return KeyboardBuilder.create_keyboard(
        buttons=[[("📋 Все коды", "view_all_codes")]]
    )


def get_custom_post_with_button_keyboard(button_text: str, button_url: str) -> InlineKeyboardMarkup:
    """Клавиатура для кастомного поста с дополнительной кнопкой"""
    return KeyboardBuilder.create_url_keyboard(
        buttons=[(button_text, button_url)],
        additional_buttons=[[("📋 Все коды", "view_all_codes")]]
    )