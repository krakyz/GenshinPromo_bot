"""
Улучшенные клавиатуры с динамической проверкой актуальности кодов
"""
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
                text=f"🎁 Активировать: {code}",
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


def get_all_codes_keyboard(codes):
    """Клавиатуры с кодами для проверки"""
    inline_keyboard = []
    
    for code in codes:
        if code.is_active:
            inline_keyboard.append([
                InlineKeyboardButton(
                    text=f"🎁 {code.code}",
                    callback_data=f"check_code_{code.code}"
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


# НОВАЯ функция для создания кнопки-подтверждения активации
def get_code_confirmation_keyboard(code: str) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру с подтверждением перехода на сайт активации
    Показывается после проверки актуальности кода
    """
    activation_url = f"https://genshin.hoyoverse.com/gift?code={code}"
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"🌐 Активировать промокод",
            url=activation_url
        )],
        [InlineKeyboardButton(
            text="🔙 Назад", 
            callback_data="view_all_codes"
        )]
    ])


# Остальные функции остаются без изменений
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


def get_admin_add_code_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру для страницы добавления кода"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")
        ]
    ])
    return keyboard


def get_admin_expire_code_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру для страницы деактивации кода"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")
        ]
    ])
    return keyboard


def get_admin_custom_post_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру для страницы создания рекламного поста"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")
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


# НОВЫЕ функции для административных клавиатур с тройным кликом

def get_admin_expire_codes_keyboard(codes: List[CodeModel]) -> InlineKeyboardMarkup:
    """Клавиатура с кнопками кодов для деактивации (для админов)"""
    inline_keyboard = []
    
    for code in codes:
        inline_keyboard.append([
            InlineKeyboardButton(
                text=f"🔥 {code.code}",
                callback_data=f"expire_code_{code.code}_1"
            )
        ])
    
    inline_keyboard.append([
        InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def get_expire_code_click_keyboard(code: str, click_count: int) -> InlineKeyboardMarkup:
    """Клавиатура с прогрессом кликов для подтверждения деактивации (для админов)"""
    
    if click_count == 1:
        button_text = f"🔸 {code} (нажми еще 2 раза)"
        callback_data = f"expire_code_{code}_2"
    elif click_count == 2:
        button_text = f"🔸🔸 {code} (нажми еще 1 раз)"
        callback_data = f"expire_code_{code}_3"
    elif click_count >= 3:
        button_text = f"❌ ДЕАКТИВИРОВАТЬ {code}"
        callback_data = f"confirm_expire_{code}"
    else:
        button_text = f"🔥 {code}"
        callback_data = f"expire_code_{code}_1"
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=button_text, callback_data=callback_data)],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_expire_code")]
    ])


def get_reset_db_click_keyboard(click_count: int) -> InlineKeyboardMarkup:
    """Клавиатура с прогрессом кликов для подтверждения сброса БД (для админов)"""
    
    if click_count == 1:
        button_text = "🔸 Сброс БД (2)"
        callback_data = "reset_click_2"
    elif click_count == 2:
        button_text = "🔸 Сброс БД (1)"
        callback_data = "reset_click_3"
    elif click_count >= 3:
        button_text = "🗑️ СБРОСИТЬ БАЗУ ДАННЫХ"
        callback_data = "confirm_reset_db"
    else:
        button_text = "🗑️ Сбросить БД"
        callback_data = "reset_click_1"
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=button_text, callback_data=callback_data)],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_database")]
    ])


def get_admin_back_keyboard() -> InlineKeyboardMarkup:
    """Простая клавиатура только с кнопкой "Назад" для админов"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
    ])

@router.callback_query(F.data == "view_all_codes")
async def view_all_codes_callback(callback: CallbackQuery):
    """Показ всех кодов с сохранением проверенных состояний"""
    try:
        user_id = callback.from_user.id
        codes = await db.get_active_codes()
        
        if not codes:
            codes_text = """🤷‍♂️ Активных промо-кодов нет

Подпишись на уведомления, чтобы не пропустить новые коды!"""
            
            is_subscribed = await UserService.get_user_subscription_status(user_id)
            keyboard = get_subscription_keyboard(is_subscribed)
        else:
            codes_text = f"""📋 Все активные промо-коды ({len(codes)}):

💡 Нажми на код, чтобы проверить его актуальность перед активацией"""
            
            # КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: Используем проверенные состояния
            checked_codes = user_checked_codes.get(user_id, {})
            inline_keyboard = []
            
            for code in codes:
                if code.is_active:
                    code_val = code.code
                    status = checked_codes.get(code_val, 'unchecked')
                    
                    if status == 'valid':
                        # Код проверен и актуален - URL-кнопка
                        activation_url = f"https://genshin.hoyoverse.com/gift?code={code_val}"
                        inline_keyboard.append([
                            InlineKeyboardButton(
                                text=f"✅ {code_val} (проверен)",
                                url=activation_url
                            )
                        ])
                    elif status == 'expired':
                        # Код истек - неактивная кнопка
                        inline_keyboard.append([
                            InlineKeyboardButton(
                                text=f"❌ {code_val} (истек)",
                                callback_data="expired_code"
                            )
                        ])
                    else:
                        # Код не проверен - кнопка для проверки
                        inline_keyboard.append([
                            InlineKeyboardButton(
                                text=f"🎁 {code_val}",
                                callback_data=f"check_code_{code_val}"
                            )
                        ])
            
            from aiogram.types import InlineKeyboardMarkup
            keyboard = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
        
        await callback.message.edit_text(
            codes_text,
            parse_mode="HTML", 
            reply_markup=keyboard
        )
        
    except Exception as e:
        logger.error(f"Ошибка просмотра кодов: {e}")
        await callback.answer("❌ Ошибка загрузки кодов", show_alert=True)
    
    await callback.answer()


# ============================================================================
# ТАКЖЕ ДОБАВЬ ОБРАБОТЧИКИ ПОДПИСКИ (если их нет)
# ============================================================================

@router.callback_query(F.data == "subscribe")
async def subscribe_callback(callback: CallbackQuery):
    """Обработчик кнопки подписки"""
    try:
        success = await db.subscribe_user(callback.from_user.id)
        
        if success:
            await callback.answer("✅ Подписка активирована!", show_alert=True)
            
            # Обновляем клавиатуру
            keyboard = get_subscription_keyboard(True)  # True = подписан
            await callback.message.edit_reply_markup(reply_markup=keyboard)
        else:
            await callback.answer("❌ Ошибка подписки", show_alert=True)
            
    except Exception as e:
        logger.error(f"Ошибка подписки: {e}")
        await callback.answer("❌ Ошибка подписки", show_alert=True)


@router.callback_query(F.data == "expired_code")
async def expired_code_callback(callback: CallbackQuery):
    """Обработчик клика по истекшему коду"""
    await callback.answer("❌ Этот промо-код больше не действует. Следи за новыми кодами!", show_alert=True)