import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Optional
import pytz
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from database import Database, PromoCode, SentMessage
from config import config

class PromoScheduler:
    def __init__(self, bot: Bot, db: Database):
        self.bot = bot
        self.db = db
        self.timezone = pytz.timezone(config.TIMEZONE)
        self.running = False
        self.check_interval = 60  # Проверка каждую минуту

    async def start(self):
        """Запуск планировщика"""
        if self.running:
            return

        self.running = True
        logging.info("Планировщик запущен")

        while self.running:
            try:
                await self.check_expired_codes()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logging.error(f"Ошибка в планировщике: {e}")
                await asyncio.sleep(60)

    async def stop(self):
        """Остановка планировщика"""
        self.running = False
        logging.info("Планировщик остановлен")

    async def check_expired_codes(self):
        """Проверка истекших промокодов"""
        try:
            active_codes = self.db.get_active_promo_codes()
            current_time = datetime.now(self.timezone)

            for promo_code in active_codes:
                if promo_code.expiry_date and current_time >= promo_code.expiry_date:
                    await self.expire_promo_code(promo_code)

        except Exception as e:
            logging.error(f"Ошибка при проверке истекших кодов: {e}")

    async def expire_promo_code(self, promo_code: PromoCode):
        """Истечение промокода и обновление всех связанных сообщений"""
        try:
            # Деактивируем промокод в БД
            if not self.db.deactivate_promo_code(promo_code.id):
                logging.error(f"Не удалось деактивировать промокод {promo_code.code}")
                return

            # Получаем все отправленные сообщения для этого промокода
            sent_messages = self.db.get_sent_messages_by_promo(promo_code.id)

            if not sent_messages:
                logging.info(f"Промокод {promo_code.code} истек, но сообщений не найдено")
                return

            # Создаем текст с истекшим промокодом
            expired_text = config.EXPIRED_PROMO_TEMPLATE.format(
                code=promo_code.code,
                description=promo_code.description,
                expiry_date=promo_code.expiry_date.strftime("%d.%m.%Y %H:%M МСК") if promo_code.expiry_date else "Не указано"
            )

            # Обновляем все сообщения
            updated_count = await self.update_expired_messages(sent_messages, expired_text)

            logging.info(f"Промокод {promo_code.code} истек. Обновлено {updated_count}/{len(sent_messages)} сообщений")

        except Exception as e:
            logging.error(f"Ошибка при истечении промокода {promo_code.code}: {e}")

    async def update_expired_messages(self, sent_messages: List[SentMessage], expired_text: str) -> int:
        """Обновление сообщений с истекшим промокодом"""
        updated_count = 0

        for sent_message in sent_messages:
            try:
                # Редактируем сообщение
                await self.bot.edit_message_text(
                    chat_id=sent_message.chat_id,
                    message_id=sent_message.message_id,
                    text=expired_text,
                    parse_mode="Markdown",
                    reply_markup=None  # Убираем кнопки
                )
                updated_count += 1

                # Небольшая задержка чтобы не превышать лимиты API
                await asyncio.sleep(0.1)

            except TelegramBadRequest as e:
                if "message is not modified" in str(e).lower():
                    # Сообщение уже обновлено
                    updated_count += 1
                elif "message to edit not found" in str(e).lower():
                    # Сообщение удалено пользователем
                    logging.debug(f"Сообщение {sent_message.message_id} не найдено")
                else:
                    logging.warning(f"Не удалось отредактировать сообщение {sent_message.message_id}: {e}")

            except TelegramForbiddenError:
                # Пользователь заблокировал бота
                logging.debug(f"Пользователь {sent_message.user_id} заблокировал бота")

            except Exception as e:
                logging.error(f"Неожиданная ошибка при редактировании сообщения {sent_message.message_id}: {e}")

        return updated_count

    async def manually_expire_code(self, promo_code_id: int) -> bool:
        """Ручная деактивация промокода"""
        try:
            promo_code = self.db.get_promo_code(promo_code_id)
            if not promo_code or not promo_code.is_active:
                return False

            await self.expire_promo_code(promo_code)
            return True

        except Exception as e:
            logging.error(f"Ошибка при ручной деактивации промокода {promo_code_id}: {e}")
            return False

    async def schedule_promo_expiry(self, promo_code: PromoCode):
        """Планирование истечения промокода"""
        if not promo_code.expiry_date:
            return

        current_time = datetime.now(self.timezone)

        # Если код уже истек, сразу деактивируем его
        if current_time >= promo_code.expiry_date:
            await self.expire_promo_code(promo_code)
        else:
            logging.info(f"Промокод {promo_code.code} будет деактивирован {promo_code.expiry_date}")