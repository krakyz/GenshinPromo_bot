import os
from dataclasses import dataclass
from typing import Optional

@dataclass
class Config:
    # Токен бота (получить у @BotFather)
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

    # ID администраторов (можно несколько, через запятую)
    ADMIN_IDS: list[int] = [int(x) for x in os.getenv("ADMIN_IDS", "123456789").split(",")]

    # Настройки базы данных
    DATABASE_PATH: str = "bot_database.db"

    # Часовой пояс (Москва)
    TIMEZONE: str = "Europe/Moscow"

    # Настройки рассылки
    MAX_MESSAGES_PER_SECOND: int = 20  # Лимит Telegram API
    BROADCAST_DELAY: float = 0.05  # Задержка между сообщениями

    # Тексты сообщений
    WELCOME_MESSAGE: str = """🎮 Добро пожаловать в бота с промокодами Genshin Impact!

🔔 Подпишитесь на рассылку, чтобы получать актуальные промокоды
💎 Все промокоды проверяются и обновляются автоматически
⏰ Уведомления о истечении кодов приходят в реальном времени"""

    SUBSCRIBE_SUCCESS: str = "✅ Вы успешно подписались на рассылку промокодов!"
    UNSUBSCRIBE_SUCCESS: str = "❌ Вы отписались от рассылки промокодов."
    ALREADY_SUBSCRIBED: str = "ℹ️ Вы уже подписаны на рассылку."
    NOT_SUBSCRIBED: str = "ℹ️ Вы не подписаны на рассылку."

    # Шаблон для промокода
    PROMO_TEMPLATE: str = """🎁 **Новый промокод Genshin Impact!**

🔑 Код: `{code}`
📋 Описание: {description}
⏳ Истекает: {expiry_date}
🌍 Сервер: Глобальный (кроме Китая)

Нажмите на кнопку ниже для активации кода!"""

    EXPIRED_PROMO_TEMPLATE: str = """❌ **Промокод истек**

🔑 Код: `{code}`
📋 Описание: {description}
⏳ Истек: {expiry_date}

К сожалению, этот промокод больше недоступен."""

config = Config()