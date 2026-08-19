import asyncio
import logging
import os
import re
import secrets
import sqlite3
from datetime import datetime, timezone

from maxapi import Bot, Dispatcher
from maxapi.types import MessageCreated

# В зависимости от версии maxapi эти классы могут импортироваться
# из другого модуля. Если твой текущий код уже с ними работает,
# оставь свои импорты.
from maxapi.types import ButtonsPayload, RequestContactButton


# =========================================================
# НАСТРОЙКИ
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

TOKEN = "f9LHodD0cOLJZ_QQj9kIYtnBMD3eCbHBwsf0UQWM34VCwzIwHu7wFVCjZ47aEkfWXziwgMn1oScOGgBlLoF5"
# ID администратора, которому разрешена команда /users.
#
# Например:
# ADMIN_IDS = {123456789}
#
# Пока можно оставить пустым, но тогда /users будет недоступна.
ADMIN_IDS = set(277114915)

DB_NAME = "users.db"


# =========================================================
# БОТ
# =========================================================

bot = Bot(TOKEN)
dp = Dispatcher()


# Пользователи, которые сейчас находятся на этапе ввода телефона.
#
# Это временное состояние.
# Основные данные хранятся в SQLite.
waiting_phone = set()


# =========================================================
# DATABASE
# =========================================================

def get_db():
    """
    Открываем соединение с SQLite.
    """
    connection = sqlite3.connect(DB_NAME)

    # Чтобы можно было обращаться к колонкам по имени.
    connection.row_factory = sqlite3.Row

    return connection


def init_db():
    """
    Создаём таблицу пользователей, если её ещё нет.
    """

    with get_db() as db:

        db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                user_id INTEGER NOT NULL UNIQUE,

                phone TEXT NOT NULL UNIQUE,

                coupon TEXT NOT NULL UNIQUE,

                created_at TEXT NOT NULL
            )
            """
        )

        # Индексы для быстрых поисков.
        db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_users_user_id
            ON users(user_id)
            """
        )

        db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_users_phone
            ON users(phone)
            """
        )

        db.commit()

    logging.info("База данных инициализирована.")


def get_user(user_id: int):
    """
    Получаем пользователя по MAX user_id.
    """

    with get_db() as db:

        cursor = db.execute(
            """
            SELECT *
            FROM users
            WHERE user_id = ?
            """,
            (user_id,)
        )

        return cursor.fetchone()


def get_users_count() -> int:
    """
    Количество участников.
    """

    with get_db() as db:

        cursor = db.execute(
            """
            SELECT COUNT(*)
            FROM users
            """
        )

        return cursor.fetchone()[0]


def create_user(
    user_id: int,
    phone: str,
    coupon: str
):
    """
    Создаём нового участника.
    """

    created_at = datetime.now(timezone.utc).isoformat()

    with get_db() as db:

        db.execute(
            """
            INSERT INTO users (
                user_id,
                phone,
                coupon,
                created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                user_id,
                phone,
                coupon,
                created_at
            )
        )

        db.commit()


# =========================================================
# PHONE
# =========================================================

def normalize_phone(phone: str) -> str:
    """
    Приводим российский номер к формату 7XXXXXXXXXX.
    """

    digits = re.sub(r"\D", "", phone)

    if digits.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]

    return digits


def is_phone(phone: str) -> bool:
    """
    Проверяем российский номер телефона.
    """

    digits = normalize_phone(phone)

    return (
        len(digits) == 11
        and digits.startswith("7")
    )


# =========================================================
# COUPON
# =========================================================

def generate_coupon() -> str:
    """
    Генерируем уникальный купон.

    Например:

    MAX-8K4P7Q
    """

    while True:

        code = (
            "MAX-"
            + secrets.token_hex(3).upper()
        )

        with get_db() as db:

            cursor = db.execute(
                """
                SELECT id
                FROM users
                WHERE coupon = ?
                """,
                (code,)
            )

            exists = cursor.fetchone()

        if not exists:
            return code


# =========================================================
# CONTACT
# =========================================================

def get_phone_from_event(event):
    """
    Пытаемся достать номер телефона из контактного
    вложения MAX.
    """

    try:

        attachments = (
            getattr(
                event.message.body,
                "attachments",
                None
            )
            or []
        )

        for attachment in attachments:

            payload = getattr(
                attachment,
                "payload",
                None
            )

            if payload is None:
                continue

            # Вариант 1 — payload.phone

            phone = getattr(
                payload,
                "phone",
                None
            )

            if phone:
                return phone

            # Вариант 2 — VCF

            vcf_info = getattr(
                payload,
                "vcf_info",
                None
            )

            if vcf_info:

                match = re.search(
                    r"TEL[^:]*:([^\r\n]+)",
                    vcf_info,
                    re.IGNORECASE
                )

                if match:
                    return match.group(1).strip()

    except Exception as e:

        logging.exception(
            f"Ошибка при получении номера "
            f"из контакта: {e}"
        )

    return None


# =========================================================
# выдача купона
# =========================================================

async def process_phone(
    event,
    user_id: int,
    phone: str
):
    """
    Обрабатываем полученный телефон.

    Здесь происходит:

    1. Проверка телефона.
    2. Проверка существующего пользователя.
    3. Создание купона.
    4. Сохранение в БД.
    5. Отправка купона.
    """

    if not is_phone(phone):

        await event.message.answer(
            "❌ Не удалось распознать номер телефона.\n\n"
            "Попробуйте поделиться номером ещё раз."
        )

        return

    phone = normalize_phone(phone)

    # Пользователь уже существует?
    existing_user = get_user(user_id)

    if existing_user:

        logging.info(
            f"Пользователь {user_id} уже есть в базе."
        )

        waiting_phone.discard(user_id)

        await event.message.answer(
            "🎟 Вы уже получали свой купон!\n\n"
            f"Ваш купон:\n\n"
            f"🎁 {existing_user['coupon']}\n\n"
            "Покажите это сообщение администратору "
            "или сделайте скриншот."
        )

        return

    # Создаём новый купон.
    coupon = generate_coupon()

    try:

        create_user(
            user_id=user_id,
            phone=phone,
            coupon=coupon
        )

    except sqlite3.IntegrityError:

        # На случай, если номер уже есть
        # у другого пользователя.

        logging.warning(
            f"Попытка повторного использования "
            f"телефона: {phone}"
        )

        await event.message.answer(
            "❌ Этот номер телефона уже "
            "использовался для получения купона."
        )

        waiting_phone.discard(user_id)

        return

    waiting_phone.discard(user_id)

    logging.info(
        f"Новый участник: "
        f"user_id={user_id}, "
        f"phone={phone}, "
        f"coupon={coupon}"
    )

    await event.message.answer(
        "🎉 Поздравляем! Вы получили новый купон! 🎁\n\n"
        f"Ваш купон:\n\n"
        f"🎟 {coupon}\n\n"
        "Покажите это сообщение администратору "
        "или выслите его скриншотом."
    )


# =========================================================
# MESSAGES
# =========================================================

@dp.message_created()
async def messages(event: MessageCreated):

    user = event.message.sender

    user_id = user.user_id

    # -----------------------------------------------------
    # Получаем текст
    # -----------------------------------------------------

    text = (
        getattr(
            event.message.body,
            "text",
            None
        )
        or ""
    ).strip()

    # -----------------------------------------------------
    # ADMIN COMMAND /users
    # -----------------------------------------------------

    if text.lower() == "/users":

        if user_id not in ADMIN_IDS:

            await event.message.answer(
                "❌ У вас нет доступа к этой команде."
            )

            return

        count = get_users_count()

        await event.message.answer(
            "👥 Статистика бота\n\n"
            f"Всего участников: {count}"
        )

        return

    # -----------------------------------------------------
    # CONTACT
    # -----------------------------------------------------

    phone = get_phone_from_event(event)

    if phone:

        logging.info(
            f"Получен номер через кнопку "
            f"от пользователя {user_id}: {phone}"
        )

        await process_phone(
            event,
            user_id,
            phone
        )

        return

    # -----------------------------------------------------
    # ЕСЛИ ЖДЁМ ТЕЛЕФОН
    # -----------------------------------------------------

    if user_id in waiting_phone:

        if is_phone(text):

            await process_phone(
                event,
                user_id,
                text
            )

        else:

            await event.message.answer(
                "❌ Это не похоже на номер телефона.\n\n"
                "Нажмите кнопку "
                "«📱 Поделиться номером» "
                "или отправьте номер вручную.\n\n"
                "Например:\n"
                "89991234567"
            )

        return

    # -----------------------------------------------------
    # ПЕРВОЕ СООБЩЕНИЕ
    # -----------------------------------------------------

    waiting_phone.add(user_id)

    # Создаём кнопку запроса контакта.
    buttons = ButtonsPayload(
        buttons=[
            [
                RequestContactButton(
                    text="📱 Поделиться номером"
                )
            ]
        ]
    ).pack()

    first_name = (
        getattr(
            user,
            "first_name",
            None
        )
        or "друг"
    )

    await event.message.answer(
        text=(
            f"{first_name}, здравствуйте! 👋\n\n"
            "Вы нашли секретный подарок! 🎁\n\n"
            "Чтобы он стал вашим, бот должен "
            "убедиться, что вы — реальный человек.\n\n"
            "Для подтверждения нажмите кнопку ниже "
            "и поделитесь своим номером телефона.\n\n"
            "Или можете отправить номер вручную."
        ),
        attachments=[buttons]
    )


# =========================================================
# MAIN
# =========================================================

async def main():

    # Создаём БД при запуске.
    init_db()

    logging.info("Бот запускается...")

    await dp.start_polling(bot)


if __name__ == "__main__":

    asyncio.run(main())
