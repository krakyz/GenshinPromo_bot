import asyncio
import logging
import sys
from datetime import datetime, timedelta
from typing import List, Optional
import pytz

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import config
from database import Database, User, PromoCode
from scheduler import PromoScheduler

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# Состояния для FSM
class AdminStates(StatesGroup):
    waiting_for_promo_code = State()
    waiting_for_promo_description = State()
    waiting_for_promo_expiry = State()
    waiting_for_ad_title = State()
    waiting_for_ad_content = State()
    waiting_for_db_reset_confirm = State()

class GenshinPromoBot:
    def __init__(self):
        self.bot = Bot(
            token=config.BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
        )
        self.dp = Dispatcher(storage=MemoryStorage())
        self.db = Database(config.DATABASE_PATH)
        self.scheduler = PromoScheduler(self.bot, self.db)
        self.timezone = pytz.timezone(config.TIMEZONE)

        # Временное хранение данных для создания промокодов
        self.temp_promo_data = {}

        self.setup_handlers()

    def setup_handlers(self):
        """Настройка обработчиков"""
        # Пользовательские команды
        self.dp.message.register(self.cmd_start, CommandStart())
        self.dp.message.register(self.cmd_help, Command("help"))

        # Админ команды
        self.dp.message.register(self.cmd_admin, Command("admin"), self.is_admin)

        # Callback обработчики
        self.dp.callback_query.register(self.handle_subscribe, F.data == "subscribe")
        self.dp.callback_query.register(self.handle_unsubscribe, F.data == "unsubscribe") 
        self.dp.callback_query.register(self.handle_admin_menu, F.data == "admin_menu")

        # Админ панель callbacks
        self.dp.callback_query.register(self.handle_add_promo, F.data == "add_promo", self.is_admin_callback)
        self.dp.callback_query.register(self.handle_view_codes, F.data == "view_codes", self.is_admin_callback)
        self.dp.callback_query.register(self.handle_statistics, F.data == "statistics", self.is_admin_callback)
        self.dp.callback_query.register(self.handle_broadcast_ad, F.data == "broadcast_ad", self.is_admin_callback)
        self.dp.callback_query.register(self.handle_db_management, F.data == "db_management", self.is_admin_callback)
        self.dp.callback_query.register(self.handle_back_to_admin, F.data == "back_to_admin", self.is_admin_callback)

        # Управление промокодами
        self.dp.callback_query.register(self.handle_deactivate_code, F.data.startswith("deactivate_"), self.is_admin_callback)
        self.dp.callback_query.register(self.handle_confirm_deactivate, F.data.startswith("confirm_deactivate_"), self.is_admin_callback)

        # Управление БД
        self.dp.callback_query.register(self.handle_reset_db, F.data == "reset_db", self.is_admin_callback)
        # ИСПРАВЛЕНО: убрана регистрация несуществующего метода handle_confirm_reset

        # FSM обработчики
        self.dp.message.register(self.process_promo_code, StateFilter(AdminStates.waiting_for_promo_code), self.is_admin)
        self.dp.message.register(self.process_promo_description, StateFilter(AdminStates.waiting_for_promo_description), self.is_admin)
        self.dp.message.register(self.process_promo_expiry, StateFilter(AdminStates.waiting_for_promo_expiry), self.is_admin)
        self.dp.message.register(self.process_ad_title, StateFilter(AdminStates.waiting_for_ad_title), self.is_admin)
        self.dp.message.register(self.process_ad_content, StateFilter(AdminStates.waiting_for_ad_content), self.is_admin)
        self.dp.message.register(self.process_db_reset_confirm, StateFilter(AdminStates.waiting_for_db_reset_confirm), self.is_admin)

        # Обработка промокодов с кнопки
        self.dp.callback_query.register(self.handle_redeem_promo, F.data.startswith("redeem_"))

    # Фильтры
    async def is_admin(self, message: Message) -> bool:
        return message.from_user.id in config.ADMIN_IDS

    async def is_admin_callback(self, callback: CallbackQuery) -> bool:
        return callback.from_user.id in config.ADMIN_IDS

    # Создание клавиатур
    def get_main_keyboard(self, user_subscribed: bool = False) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()

        if user_subscribed:
            builder.button(text="❌ Отписаться", callback_data="unsubscribe")
        else:
            builder.button(text="🔔 Подписаться", callback_data="subscribe")

        builder.adjust(1)
        return builder.as_markup()

    def get_admin_keyboard(self) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()

        builder.button(text="➕ Добавить промокод", callback_data="add_promo")
        builder.button(text="📋 Активные промокоды", callback_data="view_codes") 
        builder.button(text="📊 Статистика", callback_data="statistics")
        builder.button(text="📢 Реклама", callback_data="broadcast_ad")
        builder.button(text="🗃️ Управление БД", callback_data="db_management")

        builder.adjust(1)
        return builder.as_markup()

    def get_back_keyboard(self) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.button(text="🔙 Назад", callback_data="back_to_admin")
        return builder.as_markup()

    def get_promo_keyboard(self, promo_code: str) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()

        # Создаем ссылку на официальный сайт активации
        redeem_url = f"https://genshin.hoyoverse.com/en/gift?code={promo_code}"
        builder.button(text="🎁 Активировать код", url=redeem_url)
        builder.button(text="📋 Скопировать код", callback_data=f"redeem_{promo_code}")

        builder.adjust(1)
        return builder.as_markup()

    # Пользовательские команды
    async def cmd_start(self, message: Message):
        """Команда /start"""
        user = self.db.add_user(
            user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name
        )

        keyboard = self.get_main_keyboard(user.is_subscribed)

        await message.answer(
            config.WELCOME_MESSAGE,
            reply_markup=keyboard
        )

    async def cmd_help(self, message: Message):
        """Команда /help"""
        help_text = """
🤖 **Доступные команды:**

👤 **Для всех пользователей:**
/start - Запуск бота
/help - Справка

👑 **Для администраторов:**
/admin - Админ панель

ℹ️ **О боте:**
Этот бот автоматически уведомляет о новых промокодах Genshin Impact.
При истечении кода сообщения автоматически обновляются.

💡 **Как использовать:**
1. Подпишитесь на рассылку
2. Получайте уведомления о новых промокодах
3. Активируйте коды через официальный сайт

🔗 **Поддержка:** @your_support_username
        """

        await message.answer(help_text)

    async def cmd_admin(self, message: Message):
        """Админ панель"""
        stats = self.db.get_statistics()
        admin_text = f"""
👑 **Админ панель**

📊 **Статистика:**
• Всего пользователей: {stats['total_users']}
• Подписчиков: {stats['subscribed_users']}
• Активных промокодов: {stats['active_codes']}
• Всего промокодов: {stats['total_codes']}
• Отправлено сообщений: {stats['sent_messages']}

Выберите действие:
        """

        keyboard = self.get_admin_keyboard()
        await message.answer(admin_text, reply_markup=keyboard)

    # Callback обработчики
    async def handle_subscribe(self, callback: CallbackQuery):
        """Подписка на рассылку"""
        user_id = callback.from_user.id

        if self.db.subscribe_user(user_id):
            text = config.SUBSCRIBE_SUCCESS
        else:
            text = config.ALREADY_SUBSCRIBED

        user = self.db.get_user(user_id)
        keyboard = self.get_main_keyboard(user.is_subscribed if user else False)

        await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.answer()

    async def handle_unsubscribe(self, callback: CallbackQuery):
        """Отписка от рассылки"""
        user_id = callback.from_user.id

        if self.db.unsubscribe_user(user_id):
            text = config.UNSUBSCRIBE_SUCCESS
        else:
            text = config.NOT_SUBSCRIBED

        user = self.db.get_user(user_id)
        keyboard = self.get_main_keyboard(user.is_subscribed if user else False)

        await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.answer()

    async def handle_admin_menu(self, callback: CallbackQuery):
        """Возврат в админ меню"""
        stats = self.db.get_statistics()
        admin_text = f"""
👑 **Админ панель**

📊 **Статистика:**
• Всего пользователей: {stats['total_users']}
• Подписчиков: {stats['subscribed_users']}
• Активных промокодов: {stats['active_codes']}
• Всего промокодов: {stats['total_codes']}
• Отправлено сообщений: {stats['sent_messages']}

Выберите действие:
        """

        keyboard = self.get_admin_keyboard()
        await callback.message.edit_text(admin_text, reply_markup=keyboard)
        await callback.answer()

    # Админ функции - добавление промокода
    async def handle_add_promo(self, callback: CallbackQuery, state: FSMContext):
        """Начало добавления промокода"""
        await state.set_state(AdminStates.waiting_for_promo_code)

        text = """
➕ **Добавление промокода**

Введите промокод (только латинские буквы и цифры):
        """

        keyboard = self.get_back_keyboard()
        await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.answer()

    async def process_promo_code(self, message: Message, state: FSMContext):
        """Обработка ввода промокода"""
        code = message.text.strip().upper()

        # Валидация промокода
        if not code.isalnum() or len(code) > 50:
            await message.answer("❌ Промокод должен содержать только латинские буквы и цифры (максимум 50 символов)")
            return

        # Сохраняем код в состояние
        await state.update_data(promo_code=code)
        await state.set_state(AdminStates.waiting_for_promo_description)

        await message.answer(f"✅ Промокод: `{code}`\n\nТеперь введите описание промокода:")

    async def process_promo_description(self, message: Message, state: FSMContext):
        """Обработка описания промокода"""
        description = message.text.strip()

        if len(description) > 500:
            await message.answer("❌ Описание слишком длинное (максимум 500 символов)")
            return

        await state.update_data(description=description)
        await state.set_state(AdminStates.waiting_for_promo_expiry)

        text = """
✅ Описание сохранено.

Введите дату и время истечения промокода в формате:
`ДД.ММ.ГГГГ ЧЧ:ММ` (по московскому времени)

Например: `31.12.2024 23:59`

Или отправьте `-` если срок не ограничен.
        """

        await message.answer(text)

    async def process_promo_expiry(self, message: Message, state: FSMContext):
        """Обработка времени истечения промокода"""
        expiry_text = message.text.strip()
        expiry_date = None

        if expiry_text != "-":
            try:
                # Парсинг даты
                expiry_date = datetime.strptime(expiry_text, "%d.%m.%Y %H:%M")
                expiry_date = self.timezone.localize(expiry_date)

                # Проверяем, что дата в будущем
                if expiry_date <= datetime.now(self.timezone):
                    await message.answer("❌ Дата должна быть в будущем")
                    return

            except ValueError:
                await message.answer("❌ Неверный формат даты. Используйте: ДД.ММ.ГГГГ ЧЧ:ММ")
                return

        # Получаем данные из состояния
        data = await state.get_data()
        promo_code = data['promo_code']
        description = data['description']

        # Добавляем промокод в БД
        promo = self.db.add_promo_code(promo_code, description, expiry_date)

        if not promo:
            await message.answer(f"❌ Промокод `{promo_code}` уже существует")
            await state.clear()
            return

        # Отправляем промокод всем подписчикам
        sent_count = await self.broadcast_promo_code(promo)

        # Планируем автоматическое истечение
        if expiry_date:
            await self.scheduler.schedule_promo_expiry(promo)

        success_text = f"""
✅ **Промокод добавлен и разослан!**

🔑 Код: `{promo_code}`
📋 Описание: {description}
⏳ Истекает: {expiry_date.strftime("%d.%m.%Y %H:%M МСК") if expiry_date else "Не ограничено"}
📤 Разослано: {sent_count} пользователям
        """

        keyboard = self.get_admin_keyboard()
        await message.answer(success_text, reply_markup=keyboard)
        await state.clear()

    # Функции рассылки
    async def broadcast_promo_code(self, promo: PromoCode) -> int:
        """Рассылка промокода всем подписчикам"""
        subscribers = self.db.get_subscribed_users()
        sent_count = 0

        if not subscribers:
            logger.info("Нет подписчиков для рассылки")
            return 0

        # Формируем текст сообщения
        promo_text = config.PROMO_TEMPLATE.format(
            code=promo.code,
            description=promo.description,
            expiry_date=promo.expiry_date.strftime("%d.%m.%Y %H:%M МСК") if promo.expiry_date else "Не указано"
        )

        # Создаем клавиатуру
        keyboard = self.get_promo_keyboard(promo.code)

        # Отправляем сообщения с задержкой
        for user in subscribers:
            try:
                sent_message = await self.bot.send_message(
                    chat_id=user.user_id,
                    text=promo_text,
                    reply_markup=keyboard
                )

                # Сохраняем информацию об отправленном сообщении
                self.db.add_sent_message(
                    user_id=user.user_id,
                    promo_code_id=promo.id,
                    message_id=sent_message.message_id,
                    chat_id=user.user_id
                )

                sent_count += 1

                # Задержка для соблюдения лимитов API
                await asyncio.sleep(config.BROADCAST_DELAY)

            except TelegramForbiddenError:
                # Пользователь заблокировал бота - отписываем его
                self.db.unsubscribe_user(user.user_id)
                logger.info(f"Пользователь {user.user_id} заблокировал бота")

            except Exception as e:
                logger.error(f"Ошибка отправки сообщения пользователю {user.user_id}: {e}")

        logger.info(f"Промокод {promo.code} разослан {sent_count} пользователям")
        return sent_count

    async def handle_view_codes(self, callback: CallbackQuery):
        """Просмотр активных промокодов"""
        active_codes = self.db.get_active_promo_codes()

        if not active_codes:
            text = "📋 **Активные промокоды**\n\n❌ Нет активных промокодов"
            keyboard = self.get_back_keyboard()
        else:
            text = "📋 **Активные промокоды**\n\n"
            builder = InlineKeyboardBuilder()

            for i, promo in enumerate(active_codes[:10], 1):  # Показываем только первые 10
                expiry_str = promo.expiry_date.strftime("%d.%m.%Y %H:%M") if promo.expiry_date else "∞"
                text += f"{i}. `{promo.code}`\n"
                text += f"   📋 {promo.description}\n"
                text += f"   ⏳ Истекает: {expiry_str}\n"
                text += f"   📤 Разослано: {promo.sent_count}\n\n"

                builder.button(
                    text=f"❌ Деактивировать {promo.code}",
                    callback_data=f"deactivate_{promo.id}"
                )

            builder.button(text="🔙 Назад", callback_data="back_to_admin")
            builder.adjust(1)
            keyboard = builder.as_markup()

        await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.answer()

    async def handle_deactivate_code(self, callback: CallbackQuery):
        """Подтверждение деактивации промокода"""
        promo_id = int(callback.data.split("_")[1])
        promo = self.db.get_promo_code(promo_id)

        if not promo or not promo.is_active:
            await callback.answer("❌ Промокод не найден или уже деактивирован")
            return

        text = f"""
❓ **Подтверждение деактивации**

Вы уверены, что хотите деактивировать промокод?

🔑 Код: `{promo.code}`
📋 Описание: {promo.description}
📤 Разослано: {promo.sent_count}

⚠️ Все отправленные сообщения будут обновлены с пометкой "Промокод истек"
        """

        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Да, деактивировать", callback_data=f"confirm_deactivate_{promo_id}")
        builder.button(text="❌ Отмена", callback_data="view_codes")
        builder.adjust(1)

        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        await callback.answer()

    async def handle_confirm_deactivate(self, callback: CallbackQuery):
        """Подтвержденная деактивация промокода"""
        promo_id = int(callback.data.split("_")[2])

        success = await self.scheduler.manually_expire_code(promo_id)

        if success:
            text = "✅ Промокод успешно деактивирован и все сообщения обновлены"
        else:
            text = "❌ Ошибка при деактивации промокода"

        await callback.answer(text, show_alert=True)

        # Возвращаемся к списку кодов
        await self.handle_view_codes(callback)

    async def handle_statistics(self, callback: CallbackQuery):
        """Показ статистики"""
        stats = self.db.get_statistics()

        # Формируем список последних пользователей
        recent_users_text = ""
        for user_info in stats['recent_users']:
            name = user_info[1] or f"ID: {user_info[0]}"
            date = datetime.fromisoformat(user_info[2]).strftime("%d.%m.%Y")
            recent_users_text += f"• {name} ({date})\n"

        if not recent_users_text:
            recent_users_text = "• Нет данных\n"

        text = f"""
📊 **Детальная статистика**

👥 **Пользователи:**
• Всего: {stats['total_users']}
• Подписчики: {stats['subscribed_users']}
• Активность: {stats['subscribed_users']/max(stats['total_users'], 1)*100:.1f}%

🎁 **Промокоды:**
• Активные: {stats['active_codes']}
• Всего создано: {stats['total_codes']}
• Отправлено сообщений: {stats['sent_messages']}

👤 **Последние пользователи:**
{recent_users_text}

📅 **Обновлено:** {datetime.now(self.timezone).strftime("%d.%m.%Y %H:%M МСК")}
        """

        keyboard = self.get_back_keyboard()
        await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.answer()

    async def handle_broadcast_ad(self, callback: CallbackQuery, state: FSMContext):
        """Начало создания рекламного сообщения"""
        await state.set_state(AdminStates.waiting_for_ad_title)

        text = """
📢 **Создание рекламного сообщения**

Введите заголовок рекламного сообщения:
        """

        keyboard = self.get_back_keyboard()
        await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.answer()

    async def process_ad_title(self, message: Message, state: FSMContext):
        """Обработка заголовка рекламы"""
        title = message.text.strip()

        if len(title) > 100:
            await message.answer("❌ Заголовок слишком длинный (максимум 100 символов)")
            return

        await state.update_data(ad_title=title)
        await state.set_state(AdminStates.waiting_for_ad_content)

        await message.answer(f"✅ Заголовок: `{title}`\n\nТеперь введите содержимое рекламного сообщения:")

    async def process_ad_content(self, message: Message, state: FSMContext):
        """Обработка содержимого рекламы"""
        content = message.text.strip()

        if len(content) > 2000:
            await message.answer("❌ Содержимое слишком длинное (максимум 2000 символов)")
            return

        data = await state.get_data()
        title = data['ad_title']

        # Отправляем рекламу
        sent_count = await self.broadcast_advertisement(title, content)

        success_text = f"""
✅ **Реклама разослана!**

📢 Заголовок: {title}
📝 Содержимое: {content[:100]}{"..." if len(content) > 100 else ""}
📤 Разослано: {sent_count} пользователям
        """

        keyboard = self.get_admin_keyboard()
        await message.answer(success_text, reply_markup=keyboard)
        await state.clear()

    async def broadcast_advertisement(self, title: str, content: str) -> int:
        """Рассылка рекламы всем подписчикам"""
        subscribers = self.db.get_subscribed_users()
        sent_count = 0

        if not subscribers:
            return 0

        ad_text = f"📢 **{title}**\n\n{content}"

        for user in subscribers:
            try:
                await self.bot.send_message(
                    chat_id=user.user_id,
                    text=ad_text
                )
                sent_count += 1
                await asyncio.sleep(config.BROADCAST_DELAY)

            except TelegramForbiddenError:
                self.db.unsubscribe_user(user.user_id)

            except Exception as e:
                logger.error(f"Ошибка отправки рекламы пользователю {user.user_id}: {e}")

        logger.info(f"Реклама разослана {sent_count} пользователям")
        return sent_count

    # Управление базой данных
    async def handle_db_management(self, callback: CallbackQuery):
        """Управление базой данных"""
        stats = self.db.get_statistics()

        text = f"""
🗃️ **Управление базой данных**

📊 **Текущее состояние:**
• Пользователи: {stats['total_users']}
• Промокоды: {stats['total_codes']}
• Сообщения: {stats['sent_messages']}

⚠️ **Осторожно!** Операции с базой данных необратимы.
        """

        builder = InlineKeyboardBuilder()
        builder.button(text="🗑️ СБРОС БАЗЫ ДАННЫХ", callback_data="reset_db")
        builder.button(text="🔙 Назад", callback_data="back_to_admin")
        builder.adjust(1)

        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        await callback.answer()

    async def handle_reset_db(self, callback: CallbackQuery, state: FSMContext):
        """ИСПРАВЛЕНО: Используем FSM вместо отдельного callback"""
        await state.set_state(AdminStates.waiting_for_db_reset_confirm)

        text = """
⚠️ **ВНИМАНИЕ! ОПАСНАЯ ОПЕРАЦИЯ!**

Вы собираетесь полностью очистить базу данных.
Это действие удалит:
• Всех пользователей
• Все промокоды  
• Всю историю сообщений
• Всю статистику

Данная операция **НЕОБРАТИМА!**

Для подтверждения введите: `ПОДТВЕРДИТЬ СБРОС`
Для отмены введите любой другой текст.
        """

        await callback.message.edit_text(text)
        await callback.answer()

    async def process_db_reset_confirm(self, message: Message, state: FSMContext):
        """Обработка подтверждения сброса БД"""
        confirmation = message.text.strip()

        if confirmation == "ПОДТВЕРДИТЬ СБРОС":
            success = self.db.reset_database()

            if success:
                text = "✅ База данных успешно очищена!"
            else:
                text = "❌ Ошибка при очистке базы данных"
        else:
            text = "❌ Сброс базы данных отменен"

        keyboard = self.get_admin_keyboard()
        await message.answer(text, reply_markup=keyboard)
        await state.clear()

    async def handle_back_to_admin(self, callback: CallbackQuery, state: FSMContext):
        """Возврат в админ панель"""
        await state.clear()
        await self.handle_admin_menu(callback)

    async def handle_redeem_promo(self, callback: CallbackQuery):
        """Обработка нажатия кнопки копирования промокода"""
        promo_code = callback.data.split("_", 1)[1]
        await callback.answer(f"Промокод {promo_code} скопирован!", show_alert=True)

    # Запуск бота
    async def start_bot(self):
        """Запуск бота"""
        try:
            logger.info("Запуск бота...")

            # Запускаем планировщик
            scheduler_task = asyncio.create_task(self.scheduler.start())

            # Уведомляем админов о запуске
            for admin_id in config.ADMIN_IDS:
                try:
                    await self.bot.send_message(
                        admin_id, 
                        f"🤖 Бот запущен!\n\n⏰ {datetime.now(self.timezone).strftime('%d.%m.%Y %H:%M МСК')}"
                    )
                except:
                    pass

            logger.info("Бот успешно запущен")

            # Запускаем polling
            await self.dp.start_polling(self.bot)

        except Exception as e:
            logger.error(f"Ошибка при запуске бота: {e}")
        finally:
            await self.scheduler.stop()

    async def stop_bot(self):
        """Остановка бота"""
        logger.info("Остановка бота...")
        await self.scheduler.stop()
        await self.bot.session.close()

# Главная функция
async def main():
    """Главная функция"""
    # Проверяем конфигурацию
    if config.BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        logger.error("Необходимо установить BOT_TOKEN в переменных окружения")
        return

    if config.ADMIN_IDS == [123456789]:
        logger.error("Необходимо установить ADMIN_IDS в переменных окружения")
        return

    # Создаем и запускаем бота
    bot = GenshinPromoBot()

    try:
        await bot.start_bot()
    except KeyboardInterrupt:
        logger.info("Получен сигнал остановки")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
    finally:
        await bot.stop_bot()

if __name__ == "__main__":
    # Устанавливаем правильную политику event loop для Windows
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    asyncio.run(main())