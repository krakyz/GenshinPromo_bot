from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

def get_code_activation_keyboard(code: str) -> InlineKeyboardMarkup:
    """Создает клавиатуру с кнопкой активации кода"""
    activation_url = f"https://genshin.hoyoverse.com/gift?code={code}"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"🎁 Активировать код: {code}",
            url=activation_url
        )]
    ])
    
    return keyboard

def get_subscription_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру для управления подпиской"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔔 Подписаться", callback_data="subscribe"),
            InlineKeyboardButton(text="🔕 Отписаться", callback_data="unsubscribe")
        ]
    ])
    
    return keyboard

def get_admin_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру для админа"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ Добавить код", callback_data="admin_add_code"),
            InlineKeyboardButton(text="❌ Деактивировать код", callback_data="admin_expire_code")
        ],
        [
            InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"),
            InlineKeyboardButton(text="📋 Активные коды", callback_data="admin_active_codes")
        ]
    ])
    
    return keyboard