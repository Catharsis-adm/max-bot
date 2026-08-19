import asyncio
import logging
import re
import secrets
import sqlite3
from datetime import datetime, timezone
from calendar import monthrange

from maxapi import Bot, Dispatcher
from maxapi.types import (
    MessageCreated,
    ButtonsPayload,
    RequestContactButton,
    CallbackButton,
)


# =========================================================
# НАСТРОЙКИ
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

# ВСТАВЬ СЮДА НОВЫЙ ТОКЕН БОТА
TOKEN = "f9LHodD0cOLJZ_QQj9kIYtnBMD3eCbHBwsf0UQWM34VCwzIwHu7wFVCjZ47aEkfWXziwgMn1oScOGgBlLoF5"


# =========================================================
# АДМИНИСТРАТОРЫ
# =========================================================

ADMIN_IDS = {
    277114915
}


# =========================================================
# ID АДМИНИСТРАТОРА
# =========================================================

ADMIN_USER_ID = 174516690


# =========================================================
# DATABASE
# =========================================================

DB_NAME = "users.db"


# До этого было выдано 1267 купонов.
# Первый новый купон = 01268
INITIAL_COUPON_NUMBER = 1267


# =========================================================
# ССЫЛКИ НА ОТЗЫВЫ
# =========================================================

# ---------------------------------------------------------
# КАРЛА МАРКСА
# ---------------------------------------------------------

KARLA_YANDEX_URL = (
    "https://yandex.ru/maps/org/vr_connect/18951109146/"
    "?add-review=true&ll=53.201618%2C56.859488&z=16"
)

KARLA_2GIS_URL = (
    "https://2gis.ru/izhevsk/firm/70000001050199074/"
    "tab/reviews/addreview?m=53.201516%2C56.85975%2F16"
)

KARLA_VK_URL = (
    "https://vk.ru/reviews-202166323"
)

KARLA_GOOGLE_URL = (
    "https://www.google.com/search?q=vr+connect&oq=vr+connect+"
    "&gs_lcrp=EgZjaHJvbWUyCggAEEUYFhgeGDkyDwgBEC4YJxivARjHARiOBTIGCAIQIxgn"
    "MgcIAxAAGIAEMggIBBAAGBYYHjIGCAUQRRg8MgYIBhBFGD0yBggHEEUYPdIBCDE1NDNq"
    "MGo3qAIAsAIA&sourceid=chrome&source=chrome.ob&ie=UTF-8"
    "#lrd=0x43e139a639bba375:0x6a6865f0dd058151,3,,,,"
)


# ---------------------------------------------------------
# ТРЦ МАТРИЦА
# ---------------------------------------------------------

MATRICA_YANDEX_URL = (
    "https://yandex.ru/maps/org/vr_connect/36851840813/"
    "reviews/?add-review=true&indoorLevel=1"
    "&ll=53.124389%2C56.832935&tab=reviews&z=16.98"
)

MATRICA_2GIS_URL = (
    "https://2gis.ru/izhevsk/search/vr-%D0%B0%D1%80%D0%B5%D0%BD%D0%B0"
    "%20Connect/firm/70000001114081013/"
    "53.125482%2C56.832989/tab/reviews/addreview"
    "?m=53.163537%2C56.846359%2F14.26"
)

MATRICA_VK_URL = (
    "https://vk.ru/reviews-202166323"
)

MATRICA_GOOGLE_URL = (
    "https://www.google.com/search?q=vr+connect&oq=vr+connect+"
    "&gs_lcrp=EgZjaHJvbWUyCggAEEUYFhgeGDkyDwgBEC4YJxivARjHARiOBTIGCAIQIxgn"
    "MgcIAxAAGIAEMggIBBAAGBYYHjIGCAUQRRg8MgYIBhBFGD0yBggHEEUYPdIBCDE1NDNq"
    "MGo3qAIAsAIA&sourceid=chrome&source=chrome.ob&ie=UTF-8"
    "#lrd=0x43e139a639bba375:0x6a6865f0dd058151,3,,,,"
)


# =========================================================
# ПРИЗЫ
# =========================================================

# Дубли убраны.
#
# Все 15 вариантов имеют одинаковую вероятность.

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
# BOT
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

    connection = sqlite3.connect(
        DB_NAME
    )

    connection.row_factory = sqlite3.Row

    return connection


def init_db():

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

                created_at TEXT NOT NULL,

                location TEXT
            )
            """
        )

        # -------------------------------------------------
        # Если users уже существовала без location
        # -------------------------------------------------

        columns = db.execute(
            """
            PRAGMA table_info(users)
            """
        ).fetchall()

        column_names = {
            row["name"]
            for row in columns
        }

        if "location" not in column_names:

            db.execute(
                """
                ALTER TABLE users
                ADD COLUMN location TEXT
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
        # СЧЁТЧИК
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
        # СЧЁТЧИК
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

    # Старое поле coupon оставляем
    # для совместимости с существующей БД.

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
                created_at,
                location
            )
            VALUES (?, ?, ?, ?, NULL)
            """,
            (
                user_id,
                phone,
                legacy_coupon_value,
                created_at
            )
        )

        db.commit()


def save_user_location(
    user_id: int,
    location: str
):

    with get_db() as db:

        db.execute(
            """
            UPDATE users
            SET location = ?
            WHERE user_id = ?
            """,
            (
                location,
                user_id
            )
        )

        db.commit()

    logging.info(
        "Филиал сохранён: "
        f"user_id={user_id}, "
        f"location={location}"
    )


# =========================================================
# PHONE
# =========================================================

def normalize_phone(phone: str):

    digits = re.sub(
        r"\D",
        "",
        phone
    )

    if (
        digits.startswith("8")
        and len(digits) == 11
    ):
        digits = (
            "7" + digits[1:]
        )

    return digits


def is_phone(phone: str):

    digits = normalize_phone(
        phone
    )

    return (
        len(digits) == 11
        and digits.startswith("7")
    )


# =========================================================
# COUPON NUMBER
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
# CREATE COUPON
# =========================================================

def create_coupon(
    user_id: int
):

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
# GET USER COUPONS
# =========================================================

def get_user_coupons(
    user_id: int
):

    with get_db() as db:

        cursor = db.execute(
            """
            SELECT *
            FROM coupons
            WHERE user_id = ?
            ORDER BY coupon_number DESC
            """,
            (
                user_id,
            )
        )

        return cursor.fetchall()


# =========================================================
# CONTACT
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
            f"Ошибка получения телефона: {e}"
        )

    return None


# =========================================================
# МЕНЮ ВЫБОРА ФИЛИАЛА
# =========================================================

def create_location_menu():

    buttons = ButtonsPayload(
        buttons=[

            [
                CallbackButton(
                    text="1️⃣ Карла Маркса",
                    payload="location_karla"
                )
            ],

            [
                CallbackButton(
                    text="2️⃣ ТРЦ Матрица",
                    payload="location_matrica"
                )
            ]

        ]
    ).pack()

    return buttons


# =========================================================
# МЕНЮ ОТЗЫВОВ
# =========================================================

def create_review_menu(
    location: str
):

    if location == "karla":

        yandex_url = KARLA_YANDEX_URL
        twogis_url = KARLA_2GIS_URL
        vk_url = KARLA_VK_URL
        google_url = KARLA_GOOGLE_URL

    else:

        yandex_url = MATRICA_YANDEX_URL
        twogis_url = MATRICA_2GIS_URL
        vk_url = MATRICA_VK_URL
        google_url = MATRICA_GOOGLE_URL

    buttons = ButtonsPayload(
        buttons=[

            [
                {
                    "type": "link",
                    "text": "⭐ Яндекс Карты",
                    "url": yandex_url
                }
            ],

            [
                {
                    "type": "link",
                    "text": "⭐ 2GIS",
                    "url": twogis_url
                }
            ],

            [
                {
                    "type": "link",
                    "text": "⭐ ВКонтакте",
                    "url": vk_url
                }
            ],

            [
                {
                    "type": "link",
                    "text": "⭐ Google",
                    "url": google_url
                }
            ],

            [
                {
                    "type": "link",
                    "text": "👨‍💼 Написать Администратору",
                    "url": f"max://user/{ADMIN_USER_ID}"
                }
            ]

        ]
    ).pack()

    return buttons


# =========================================================
# МЕНЮ "МОИ КУПОНЫ"
# =========================================================

def create_my_coupons_menu():

    buttons = ButtonsPayload(
        buttons=[

            [
                CallbackButton(
                    text="🎟 Мои купоны",
                    payload="my_coupons"
                )
            ]

        ]
    ).pack()

    return buttons


# =========================================================
# ОТПРАВИТЬ МЕНЮ ОТЗЫВОВ
# =========================================================

async def send_review_menu(
    event,
    user_id: int
):

    user = get_user(
        user_id
    )

    if user is None:

        return

    location = user["location"]

    if location == "karla":

        location_name = (
            "Карла Маркса"
        )

    elif location == "matrica":

        location_name = (
            "ТРЦ Матрица"
        )

    else:

        return

    buttons = create_review_menu(
        location
    )

    await event.message.answer(

        text=(

            f"Спасибо! ❤️\n\n"

            f"Вы выбрали: "
            f"📍 {location_name}\n\n"

            "Если хотите поддержать нас, "
            "будем очень благодарны за отзыв "
            "на одной из площадок ниже 👇"
        ),

        attachments=[
            buttons
        ]
    )


# =========================================================
# ОТПРАВИТЬ МЕНЮ ВЫБОРА ФИЛИАЛА
# =========================================================

async def ask_location(
    event
):

    buttons = create_location_menu()

    await event.message.answer(

        text=(

            "📍 Где вы отдыхали?\n\n"

            "Выберите филиал, который "
            "вы посещали:"
        ),

        attachments=[
            buttons
        ]
    )


# =========================================================
# МОИ КУПОНЫ
# =========================================================

async def show_my_coupons(
    event,
    user_id: int
):

    coupons = get_user_coupons(
        user_id
    )

    if not coupons:

        await event.message.answer(
            "🎟 У вас пока нет купонов."
        )

        return

    text = (
        "🎟 ВАШИ КУПОНЫ\n\n"
    )

    for coupon in coupons:

        try:

            expires_at = datetime.fromisoformat(
                coupon["expires_at"]
            )

            expires_text = (
                expires_at.strftime(
                    "%d.%m.%Y"
                )
            )

        except Exception:

            expires_text = (
                coupon["expires_at"]
            )

        text += (

            "━━━━━━━━━━━━━━━━━━\n\n"

            f"🎟 Купон: "
            f"{coupon['coupon_number']:05d}\n\n"

            f"🎁 Приз:\n"
            f"{coupon['prize']}\n\n"

            f"⏳ Действует до: "
            f"{expires_text}\n\n"
        )

    await event.message.answer(
        text
    )


# =========================================================
# ADMIN /USERS
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

        cursor = db.execute(
            """
            SELECT COUNT(*)
            FROM users
            WHERE location = 'karla'
            """
        )

        karla_count = (
            cursor.fetchone()[0]
        )

        cursor = db.execute(
            """
            SELECT COUNT(*)
            FROM users
            WHERE location = 'matrica'
            """
        )

        matrica_count = (
            cursor.fetchone()[0]
        )

    await event.message.answer(

        "👑 СТАТИСТИКА БОТА\n\n"

        f"👥 Участников: "
        f"{users_count}\n\n"

        f"🎟 Выдано купонов: "
        f"{coupons_count}\n\n"

        "📍 ФИЛИАЛЫ:\n\n"

        f"Карла Маркса: "
        f"{karla_count}\n"

        f"ТРЦ Матрица: "
        f"{matrica_count}"
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
    # Пользователь уже есть
    # -----------------------------------------------------

    existing_user = get_user(
        user_id
    )

    if existing_user:

        waiting_phone.discard(
            user_id
        )

        await event.message.answer(

            "ℹ️ Вы уже зарегистрированы.\n\n"

            "Повторная отправка номера "
            "не создаёт новый купон."
        )

        # Если филиал уже выбран,
        # показываем меню отзывов.

        if existing_user["location"]:

            await send_review_menu(
                event,
                user_id
            )

        else:

            await ask_location(
                event
            )

        return

    # -----------------------------------------------------
    # Телефон уже принадлежит другому пользователю
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
    # Регистрируем пользователя
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
        "Новый участник: "
        f"user_id={user_id}"
    )

    # -----------------------------------------------------
    # ВЫДАЁМ ПЕРВЫЙ И ЕДИНСТВЕННЫЙ КУПОН
    # -----------------------------------------------------

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

            "❌ Произошла ошибка "
            "при создании купона.\n\n"
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

    # -----------------------------------------------------
    # ПОКАЗЫВАЕМ КУПОН
    # -----------------------------------------------------

    await event.message.answer(

        "🎉 ПОЗДРАВЛЯЕМ!\n\n"

        "Вы получили свой купон! 🎁\n\n"

        f"🎟 НОМЕР КУПОНА:\n"
        f"{coupon_number:05d}\n\n"

        f"🎁 ВАШ ПРИЗ:\n"
        f"{prize}\n\n"

        f"📅 Выдан: "
        f"{created_text}\n"

        f"⏳ Действует до: "
        f"{expires_text}\n\n"

        "Покажите это сообщение "
        "администратору или сделайте "
        "скриншот."
    )

    # -----------------------------------------------------
    # СПРАШИВАЕМ ФИЛИАЛ
    # -----------------------------------------------------

    await ask_location(
        event
    )


# =========================================================
# CALLBACK
# =========================================================

@dp.message_callback()
async def callbacks(
    event
):

    user_id = (
        event.user.user_id
    )

    payload = (
        getattr(
            event,
            "payload",
            None
        )
        or ""
    )

    logging.info(
        "CALLBACK | "
        f"user_id={user_id} | "
        f"payload={payload}"
    )

    # =====================================================
    # КАРЛА МАРКСА
    # =====================================================

    if payload == "location_karla":

        save_user_location(
            user_id,
            "karla"
        )

        await event.message.answer(

            "📍 Отлично!\n\n"

            "Вы выбрали филиал "
            "на Карла Маркса.\n\n"

            "Будем очень благодарны "
            "за ваш отзыв ❤️\n\n"

            "Выберите площадку:"
        )

        buttons = create_review_menu(
            "karla"
        )

        await event.message.answer(
            "👇 Оставить отзыв:",
            attachments=[
                buttons
            ]
        )

        return

    # =====================================================
    # ТРЦ МАТРИЦА
    # =====================================================

    if payload == "location_matrica":

        save_user_location(
            user_id,
            "matrica"
        )

        await event.message.answer(

            "📍 Отлично!\n\n"

            "Вы выбрали филиал "
            "в ТРЦ Матрица.\n\n"

            "Будем очень благодарны "
            "за ваш отзыв ❤️\n\n"

            "Выберите площадку:"
        )

        buttons = create_review_menu(
            "matrica"
        )

        await event.message.answer(
            "👇 Оставить отзыв:",
            attachments=[
                buttons
            ]
        )

        return

    # =====================================================
    # МОИ КУПОНЫ
    # =====================================================

    if payload == "my_coupons":

        await show_my_coupons(
            event,
            user_id
        )

        return


# =========================================================
# MESSAGE CREATED
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
    # ТЕКСТ
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
            "Получен номер: "
            f"user_id={user_id}"
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
            "и поделитесь своим номером."
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

