import asyncio
import logging
import re
import secrets
import sqlite3
from datetime import datetime, timezone
from calendar import monthrange

from maxapi import Bot, Dispatcher
from maxapi.types import MessageCreated
from maxapi.types import ButtonsPayload, RequestContactButton


# =========================================================
# НАСТРОЙКИ
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

TOKEN = "f9LHodD0cOLJZ_QQj9kIYtnBMD3eCbHBwsf0UQWM34VCwzIwHu7wFVCjZ47aEkfWXziwgMn1oScOGgBlLoF5"

# ID администраторов
ADMIN_IDS = {
    277114915
}

DB_NAME = "users.db"

# До этого было выдано 1267 купонов.
# Первый купон этого бота будет 01268.
INITIAL_COUPON_NUMBER = 1267


# =========================================================
# ССЫЛКИ ДЛЯ БУДУЩЕГО МЕНЮ
# =========================================================
#
# Пока поставлены заглушки.
# Позже сюда вставим реальные ссылки.
#

YANDEX_REVIEW_URL = "https://yandex.ru/"

TWO_GIS_REVIEW_URL = "https://2gis.ru/"

VK_REVIEW_URL = "https://vk.com/"

GOOGLE_REVIEW_URL = "https://www.google.com/"


# =========================================================
# ПРИЗЫ
# =========================================================

# Дубли убраны.
# Все 15 призов имеют одинаковую вероятность.

PRIZES = [
    "1 час игры в VR шлеме",

    "1 час игры на любой консоли",

    "15 минут игры в VR Автосимуляторе",

    "30 минут игры на консоли",

    "1 час в VR шлеме, при аренде от 1 часа VR шлема",

    "1 час игр на консоли (XBox / PS5), "
    "при аренде от 1 часа VR шлема",

    "15 минут игр на VR Автосимуляторе, "
    "при аренде 15 минут на Автосимуляторе",

    "30 минут игры на консоли (XBox / PS5), "
    "при аренде от 1 часа VR шлема",

    "Бонус 500 ₽ при покупке сертификата от 1000 ₽",

    "Скидка 500 ₽ на покупку любого абонемента",

    "Скидка 500 ₽ при аренде VR шлема на дом",

    "Скидка 300 ₽ на второй час аренды VR шлема",

    "1 час игр на консоли (XBox / PS5), "
    "при аренде от 1 часа аренды консоли",

    "2 часа игры в VR",

    "15 минут игр на автосимуляторе, "
    "при аренде от 1 часа VR шлема",
]


# =========================================================
# БОТ
# =========================================================

bot = Bot(TOKEN)

dp = Dispatcher()


# =========================================================
# ВРЕМЕННОЕ СОСТОЯНИЕ
# =========================================================

waiting_phone = set()


# =========================================================
# DATABASE
# =========================================================

def get_db():
    connection = sqlite3.connect(DB_NAME)

    connection.row_factory = sqlite3.Row

    return connection


def init_db():
    """
    Создаём необходимые таблицы.

    Существующая users.db НЕ удаляется.
    """

    with get_db() as db:

        # =================================================
        # USERS
        # =================================================

        db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                user_id INTEGER NOT NULL UNIQUE,

                phone TEXT NOT NULL UNIQUE,

                coupon TEXT,

                created_at TEXT NOT NULL
            )
            """
        )

        # =================================================
        # COUPONS
        # =================================================

        db.execute(
            """
            CREATE TABLE IF NOT EXISTS coupons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                coupon_number INTEGER NOT NULL UNIQUE,

                user_id INTEGER NOT NULL,

                prize TEXT NOT NULL,

                created_at TEXT NOT NULL,

                expires_at TEXT NOT NULL,

                status TEXT NOT NULL DEFAULT 'active',

                FOREIGN KEY (user_id)
                    REFERENCES users(user_id)
            )
            """
        )

        # =================================================
        # СЧЁТЧИК КУПОНОВ
        # =================================================

        db.execute(
            """
            CREATE TABLE IF NOT EXISTS coupon_counter (
                id INTEGER PRIMARY KEY CHECK (id = 1),

                current_number INTEGER NOT NULL
            )
            """
        )

        # =================================================
        # ИНДЕКСЫ
        # =================================================

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

        db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_coupons_user_id
            ON coupons(user_id)
            """
        )

        # =================================================
        # ИНИЦИАЛИЗИРУЕМ СЧЁТЧИК
        # =================================================

        cursor = db.execute(
            """
            SELECT current_number
            FROM coupon_counter
            WHERE id = 1
            """
        )

        counter = cursor.fetchone()

        if counter is None:

            db.execute(
                """
                INSERT INTO coupon_counter (
                    id,
                    current_number
                )
                VALUES (1, ?)
                """,
                (
                    INITIAL_COUPON_NUMBER,
                )
            )

            logging.info(
                "Счётчик купонов установлен: "
                f"{INITIAL_COUPON_NUMBER}"
            )

        db.commit()

    logging.info(
        "База данных инициализирована."
    )


# =========================================================
# USERS
# =========================================================

def get_user(user_id: int):

    with get_db() as db:

        cursor = db.execute(
            """
            SELECT *
            FROM users
            WHERE user_id = ?
            """,
            (
                user_id,
            )
        )

        return cursor.fetchone()


def get_user_by_phone(phone: str):

    with get_db() as db:

        cursor = db.execute(
            """
            SELECT *
            FROM users
            WHERE phone = ?
            """,
            (
                phone,
            )
        )

        return cursor.fetchone()


def get_users_count():

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
    phone: str
):

    created_at = datetime.now(
        timezone.utc
    ).isoformat()

    # Это поле осталось для совместимости
    # со старой версией users.db.
    legacy_coupon_value = (
        f"PROFILE-{user_id}"
    )

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
                legacy_coupon_value,
                created_at
            )
        )

        db.commit()


# =========================================================
# PHONE
# =========================================================

def normalize_phone(phone: str) -> str:

    digits = re.sub(
        r"\D",
        "",
        phone
    )

    if (
        digits.startswith("8")
        and len(digits) == 11
    ):
        digits = "7" + digits[1:]

    return digits


def is_phone(phone: str) -> bool:

    digits = normalize_phone(phone)

    return (
        len(digits) == 11
        and digits.startswith("7")
    )


# =========================================================
# СЛЕДУЮЩИЙ НОМЕР КУПОНА
# =========================================================

def get_next_coupon_number():

    with get_db() as db:

        cursor = db.execute(
            """
            SELECT current_number
            FROM coupon_counter
            WHERE id = 1
            """
        )

        row = cursor.fetchone()

        if row is None:

            current_number = (
                INITIAL_COUPON_NUMBER
            )

            db.execute(
                """
                INSERT INTO coupon_counter (
                    id,
                    current_number
                )
                VALUES (1, ?)
                """,
                (
                    current_number,
                )
            )

        else:

            current_number = (
                row["current_number"]
            )

        next_number = (
            current_number + 1
        )

        db.execute(
            """
            UPDATE coupon_counter
            SET current_number = ?
            WHERE id = 1
            """,
            (
                next_number,
            )
        )

        db.commit()

    return current_number


# =========================================================
# + 1 МЕСЯЦ
# =========================================================

def add_one_month(dt):

    year = dt.year

    month = dt.month + 1

    if month == 13:

        month = 1

        year += 1

    last_day = monthrange(
        year,
        month
    )[1]

    day = min(
        dt.day,
        last_day
    )

    return dt.replace(
        year=year,
        month=month,
        day=day
    )


# =========================================================
# СОЗДАНИЕ КУПОНА
# =========================================================

def create_coupon(user_id: int):

    created_at = datetime.now(
        timezone.utc
    )

    expires_at = add_one_month(
        created_at
    )

    coupon_number = (
        get_next_coupon_number()
    )

    # Все призы равновероятны.
    prize = secrets.choice(
        PRIZES
    )

    with get_db() as db:

        db.execute(
            """
            INSERT INTO coupons (
                coupon_number,
                user_id,
                prize,
                created_at,
                expires_at,
                status
            )
            VALUES (?, ?, ?, ?, ?, 'active')
            """,
            (
                coupon_number,
                user_id,
                prize,
                created_at.isoformat(),
                expires_at.isoformat()
            )
        )

        db.commit()

    logging.info(
        "КУПОН ВЫДАН | "
        f"{coupon_number:05d} | "
        f"user_id={user_id} | "
        f"{prize}"
    )

    return (
        coupon_number,
        prize,
        created_at,
        expires_at
    )


# =========================================================
# КОЛИЧЕСТВО КУПОНОВ ПОЛЬЗОВАТЕЛЯ
# =========================================================

def get_user_coupons_count(
    user_id: int
):

    with get_db() as db:

        cursor = db.execute(
            """
            SELECT COUNT(*)
            FROM coupons
            WHERE user_id = ?
            """,
            (
                user_id,
            )
        )

        return cursor.fetchone()[0]


# =========================================================
# ПОЛУЧЕНИЕ КОНТАКТА
# =========================================================

def get_phone_from_event(event):

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

            phone = getattr(
                payload,
                "phone",
                None
            )

            if phone:
                return phone

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

                    return (
                        match.group(1).strip()
                    )

    except Exception as e:

        logging.exception(
            "Ошибка получения "
            f"телефона: {e}"
        )

    return None


# =========================================================
# МЕНЮ ПОСЛЕ ПОЛУЧЕНИЯ КУПОНА
# =========================================================

def create_main_menu():

    buttons = ButtonsPayload(
        buttons=[

            [
                {
                    "type": "link",
                    "text": "🎟 Мои купоны",
                    "url": "https://example.com"
                }
            ],

            [
                {
                    "type": "link",
                    "text": "⭐ Отзыв в Яндекс Картах",
                    "url": YANDEX_REVIEW_URL
                }
            ],

            [
                {
                    "type": "link",
                    "text": "⭐ Отзыв в 2GIS",
                    "url": TWO_GIS_REVIEW_URL
                }
            ],

            [
                {
                    "type": "link",
                    "text": "⭐ Отзыв в ВК",
                    "url": VK_REVIEW_URL
                }
            ],

            [
                {
                    "type": "link",
                    "text": "⭐ Отзыв в Google",
                    "url": GOOGLE_REVIEW_URL
                }
            ]

        ]
    ).pack()

    return buttons


# =========================================================
# ОТПРАВКА КУПОНА
# =========================================================

async def send_first_coupon(
    event,
    user_id: int
):

    try:

        (
            coupon_number,
            prize,
            created_at,
            expires_at
        ) = create_coupon(
            user_id
        )

    except Exception as e:

        logging.exception(
            f"Ошибка создания купона: {e}"
        )

        await event.message.answer(
            "❌ Произошла ошибка при создании "
            "купона.\n\n"
            "Попробуйте ещё раз."
        )

        return

    created_text = (
        created_at.strftime(
            "%d.%m.%Y"
        )
    )

    expires_text = (
        expires_at.strftime(
            "%d.%m.%Y"
        )
    )

    await event.message.answer(

        "🎉 ПОЗДРАВЛЯЕМ!\n\n"

        "Вы получили новый купон! 🎁\n\n"

        f"🎟 НОМЕР КУПОНА:\n"
        f"{coupon_number:05d}\n\n"

        f"🎁 ВАШ ПРИЗ:\n"
        f"{prize}\n\n"

        f"📅 Выдан: {created_text}\n"
        f"⏳ Действует до: {expires_text}\n\n"

        "Покажите это сообщение "
        "администратору или сделайте скриншот."
    )

    # =====================================================
    # МЕНЮ
    # =====================================================

    buttons = create_main_menu()

    await event.message.answer(

        "👇 Что хотите сделать?",

        attachments=[
            buttons
        ]
    )


# =========================================================
# ОБРАБОТКА ТЕЛЕФОНА
# =========================================================

async def process_phone(
    event,
    user_id: int,
    phone: str
):

    # -----------------------------------------------------
    # Проверяем номер
    # -----------------------------------------------------

    if not is_phone(phone):

        await event.message.answer(
            "❌ Не удалось распознать "
            "номер телефона.\n\n"
            "Попробуйте поделиться "
            "номером ещё раз."
        )

        return

    phone = normalize_phone(
        phone
    )

    # -----------------------------------------------------
    # Проверяем MAX user_id
    # -----------------------------------------------------

    existing_user = get_user(
        user_id
    )

    if existing_user:

        waiting_phone.discard(
            user_id
        )

        coupons_count = (
            get_user_coupons_count(
                user_id
            )
        )

        logging.info(
            "Повторная отправка номера: "
            f"user_id={user_id}. "
            "Новый купон НЕ выдаём."
        )

        await event.message.answer(

            "ℹ️ Вы уже зарегистрированы.\n\n"

            f"🎟 Ваших купонов: "
            f"{coupons_count}\n\n"

            "Повторная отправка номера "
            "не создаёт новый купон."
        )

        # Показываем меню снова.

        buttons = create_main_menu()

        await event.message.answer(
            "👇 Ваше меню:",
            attachments=[
                buttons
            ]
        )

        return

    # -----------------------------------------------------
    # Проверяем телефон
    # -----------------------------------------------------

    phone_owner = get_user_by_phone(
        phone
    )

    if phone_owner:

        waiting_phone.discard(
            user_id
        )

        await event.message.answer(
            "❌ Этот номер телефона уже "
            "зарегистрирован в системе."
        )

        return

    # -----------------------------------------------------
    # Создаём пользователя
    # -----------------------------------------------------

    try:

        create_user(
            user_id=user_id,
            phone=phone
        )

    except sqlite3.IntegrityError:

        logging.exception(
            "Ошибка сохранения пользователя."
        )

        await event.message.answer(
            "❌ Не удалось сохранить "
            "данные.\n\n"
            "Попробуйте ещё раз."
        )

        return

    waiting_phone.discard(
        user_id
    )

    logging.info(
        "Зарегистрирован новый участник: "
        f"user_id={user_id}, "
        f"phone={phone}"
    )

    # -----------------------------------------------------
    # ВЫДАЁМ РОВНО ОДИН КУПОН
    # -----------------------------------------------------

    await send_first_coupon(
        event,
        user_id
    )


# =========================================================
# /USERS
# =========================================================

async def handle_users(
    event
):

    user_id = (
        event.message.sender.user_id
    )

    if user_id not in ADMIN_IDS:

        await event.message.answer(
            "❌ У вас нет доступа "
            "к этой команде."
        )

        return

    users_count = (
        get_users_count()
    )

    with get_db() as db:

        cursor = db.execute(
            """
            SELECT COUNT(*)
            FROM coupons
            """
        )

        coupons_count = (
            cursor.fetchone()[0]
        )

    await event.message.answer(

        "👑 СТАТИСТИКА БОТА\n\n"

        f"👥 Участников: "
        f"{users_count}\n\n"

        f"🎟 Выдано купонов: "
        f"{coupons_count}"
    )


# =========================================================
# ОСНОВНОЙ ОБРАБОТЧИК
# =========================================================

@dp.message_created()
async def messages(
    event: MessageCreated
):

    user = (
        event.message.sender
    )

    user_id = (
        user.user_id
    )

    # -----------------------------------------------------
    # Текст
    # -----------------------------------------------------

    text = (
        getattr(
            event.message.body,
            "text",
            None
        )
        or ""
    ).strip()

    text_lower = text.lower()

    # -----------------------------------------------------
    # /users
    # -----------------------------------------------------

    if text_lower == "/users":

        await handle_users(
            event
        )

        return

    # -----------------------------------------------------
    # КОНТАКТ
    # -----------------------------------------------------

    phone = get_phone_from_event(
        event
    )

    if phone:

        logging.info(
            "Получен номер через контакт: "
            f"user_id={user_id}, "
            f"phone={phone}"
        )

        await process_phone(
            event,
            user_id,
            phone
        )

        return

    # -----------------------------------------------------
    # ЕСЛИ ЖДЁМ НОМЕР
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

                "❌ Это не похоже "
                "на номер телефона.\n\n"

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

    waiting_phone.add(
        user_id
    )

    # -----------------------------------------------------
    # КНОПКА ПОДЕЛИТЬСЯ НОМЕРОМ
    # -----------------------------------------------------

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

            f"{first_name}, "
            "здравствуйте! 👋\n\n"

            "Вы нашли секретный подарок! 🎁\n\n"

            "Чтобы получить его, "
            "нам необходимо подтвердить "
            "ваш номер телефона.\n\n"

            "Нажмите кнопку ниже "
            "и поделитесь своим номером.\n\n"

            "Или можете отправить номер "
            "вручную."
        ),

        attachments=[
            buttons
        ]
    )


# =========================================================
# MAIN
# =========================================================

async def main():

    init_db()

    logging.info(
        "Бот запускается..."
    )

    logging.info(
        f"Участников в базе: "
        f"{get_users_count()}"
    )

    await dp.start_polling(
        bot
    )


# =========================================================
# START
# =========================================================

if __name__ == "__main__":

    asyncio.run(
        main()
    )
