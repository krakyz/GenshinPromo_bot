import os
from typing import List

class Config:
    def __init__(self):
        # Токен бота (получить у @BotFather)
        self.BOT_TOKEN: str = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

        # ID администраторов (можно несколько, через запятую)
        admin_ids_str = os.getenv("ADMIN_IDS", "123456789")
        self.ADMIN_IDS: List[int] = [int(x.strip()) for x in admin_ids_str.split(",") if x.strip()]

        # Настройки базы данных
        self.DATABASE_PATH: str = "bot_database.db"

        # Часовой пояс (Москва)
        self.TIMEZONE: str = "Europe/Moscow"

        # Настройки рассылки
        self.MAX_MESSAGES_PER_SECOND: int = 20  # Лимит Telegram API
        self.BROADCAST_DELAY: float = 0.05  # Задержка между сообщениями

        # Тексты сообщений
        self.WELCOME_MESSAGE: str = """🎮 Добро пожаловать в бота с промокодами Genshin Impact!

🔔 Подпишитесь на рассылку, чтобы получать актуальные промокоды
💎 Все промокоды проверяются и обновляются автоматически
⏰ Уведомления о истечении кодов приходят в реальном времени"""

        self.SUBSCRIBE_SUCCESS: str = "✅ Вы успешно подписались на рассылку промокодов!"
        self.UNSUBSCRIBE_SUCCESS: str = "❌ Вы отписались от рассылки промокодов."
        self.ALREADY_SUBSCRIBED: str = "ℹ️ Вы уже подписаны на рассылку."
        self.NOT_SUBSCRIBED: str = "ℹ️ Вы не подписаны на рассылку."

        # Шаблон для промокода
        self.PROMO_TEMPLATE: str = """🎁 **Новый промокод Genshin Impact!**

🔑 Код: `{code}`
📋 Описание: {description}
⏳ Истекает: {expiry_date}
🌍 Сервер: Глобальный (кроме Китая)

Нажмите на кнопку ниже для активации кода!"""

        self.EXPIRED_PROMO_TEMPLATE: str = """❌ **Промокод истек**

🔑 Код: `{code}`
📋 Описание: {description}
⏳ Истек: {expiry_date}

К сожалению, этот промокод больше недоступен."""

config = Config()