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
)


# =========================================================
# ЛОГИ
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)


# =========================================================
# НАСТРОЙКИ
# =========================================================

# ВСТАВЬ НОВЫЙ ТОКЕН БОТА
TOKEN = "ВСТАВЬ_НОВЫЙ_ТОКЕН_СЮДА"

DB_NAME = "users.db"


# =========================================================
# АДМИНИСТРАТОРЫ
# =========================================================

ADMIN_IDS = {
    174516690
}

# Администратор филиала Карла Маркса
ADMIN_KARLA_ID = 174451690

# Администратор филиала ТРЦ Матрица
ADMIN_MATRICA_ID = 314256668


# =========================================================
# КУПОНЫ
# =========================================================

INITIAL_COUPON_NUMBER = 1267


# =========================================================
# БОТ
# =========================================================

bot = Bot(TOKEN)
dp = Dispatcher()


# =========================================================
# ВРЕМЕННЫЕ СОСТОЯНИЯ
# =========================================================

# Здесь находятся ТОЛЬКО новые пользователи,
# которым действительно нужно получить телефон.

waiting_phone = set()


# =========================================================
# ПРИЗЫ
# =========================================================

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
# ССЫЛКИ — КАРЛА МАРКСА
# =========================================================

KARLA_YANDEX = (
    "https://yandex.ru/maps/org/vr_connect/18951109146/"
    "?add-review=true&ll=53.201618%2C56.859488&z=16"
)

KARLA_2GIS = (
    "https://2gis.ru/reviews/70000001050199074/"
    "addReview?utm_source=lk"
)

KARLA_VK = (
    "https://vk.ru/reviews-202166323"
)

KARLA_GOOGLE = (
    "https://g.page/r/CVGBBd3wZWhqEBM/review"
)


# =========================================================
# ССЫЛКИ — ТРЦ МАТРИЦА
# =========================================================

MATRICA_YANDEX = (
    "https://yandex.ru/maps/org/vr_connect/36851840813/"
    "reviews/?add-review=true&indoorLevel=1"
    "&ll=53.124389%2C56.832935&tab=reviews&z=16.98"
)

MATRICA_2GIS = (
    "https://2gis.ru/reviews/70000001114081013/"
    "addReview?utm_source=lk"
)

MATRICA_VK = (
    "https://vk.ru/reviews-202166323"
)

MATRICA_GOOGLE = (
    "https://g.page/r/CTkdqTcLtOo-EBM/review"
)


# =========================================================
# DATABASE
# =========================================================

def get_db():

    db = sqlite3.connect(DB_NAME)

    db.row_factory = sqlite3.Row

    return db


def init_db():

    with get_db() as db:

        # -------------------------------------------------
        # USERS
        # -------------------------------------------------

        db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                phone TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                location TEXT
            )
            """
        )

        # -------------------------------------------------
        # Проверяем старую базу
        # -------------------------------------------------

        columns = db.execute(
            "PRAGMA table_info(users)"
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

        # -------------------------------------------------
        # COUPONS
        # -------------------------------------------------

        db.execute(
            """
            CREATE TABLE IF NOT EXISTS coupons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                coupon_number INTEGER NOT NULL UNIQUE,

                user_id INTEGER NOT NULL,

                prize TEXT NOT NULL,

                created_at TEXT NOT NULL,

                expires_at TEXT NOT NULL,

                status TEXT NOT NULL DEFAULT 'active'
            )
            """
        )

        # -------------------------------------------------
        # COUNTER
        # -------------------------------------------------

        db.execute(
            """
            CREATE TABLE IF NOT EXISTS coupon_counter (
                id INTEGER PRIMARY KEY CHECK (id = 1),

                current_number INTEGER NOT NULL
            )
            """
        )

        counter = db.execute(
            """
            SELECT current_number
            FROM coupon_counter
            WHERE id = 1
            """
        ).fetchone()

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

        # -------------------------------------------------
        # INDEXES
        # -------------------------------------------------

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

        db.commit()

    logging.info(
        "База данных инициализирована."
    )


# =========================================================
# USERS
# =========================================================

def get_user(user_id):

    with get_db() as db:

        return db.execute(
            """
            SELECT *
            FROM users
            WHERE user_id = ?
            """,
            (
                user_id,
            )
        ).fetchone()


def get_user_by_phone(phone):

    with get_db() as db:

        return db.execute(
            """
            SELECT *
            FROM users
            WHERE phone = ?
            """,
            (
                phone,
            )
        ).fetchone()


def get_users_count():

    with get_db() as db:

        return db.execute(
            """
            SELECT COUNT(*)
            FROM users
            """
        ).fetchone()[0]


def create_user(
    user_id,
    phone
):

    created_at = datetime.now(
        timezone.utc
    ).isoformat()

    with get_db() as db:

        db.execute(
            """
            INSERT INTO users (
                user_id,
                phone,
                created_at,
                location
            )
            VALUES (?, ?, ?, NULL)
            """,
            (
                user_id,
                phone,
                created_at
            )
        )

        db.commit()


def save_location(
    user_id,
    location
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
        f"Пользователю {user_id} "
        f"установлен филиал: {location}"
    )


# =========================================================
# ТЕЛЕФОН
# =========================================================

def normalize_phone(phone):

    digits = re.sub(
        r"\D",
        "",
        phone
    )

    if (
        len(digits) == 11
        and digits.startswith("8")
    ):

        digits = "7" + digits[1:]

    return digits


def is_phone(phone):

    digits = normalize_phone(
        phone
    )

    return (
        len(digits) == 11
        and digits.startswith("7")
    )


# =========================================================
# НОМЕР КУПОНА
# =========================================================

def get_next_coupon_number():

    with get_db() as db:

        row = db.execute(
            """
            SELECT current_number
            FROM coupon_counter
            WHERE id = 1
            """
        ).fetchone()

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
# +1 МЕСЯЦ
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

def create_coupon(user_id):

    created_at = datetime.now(
        timezone.utc
    )

    expires_at = add_one_month(
        created_at
    )

    coupon_number = (
        get_next_coupon_number()
    )

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

    return (
        coupon_number,
        prize,
        created_at,
        expires_at
    )


# =========================================================
# ПОЛУЧЕНИЕ ТЕЛЕФОНА
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
# КНОПКИ ФИЛИАЛОВ
# =========================================================

def location_buttons():

    return ButtonsPayload(
        buttons=[
            [
                {
                    "type": "callback",
                    "text": "1️⃣ Карла Маркса",
                    "payload": "location_karla"
                }
            ],
            [
                {
                    "type": "callback",
                    "text": "2️⃣ ТРЦ Матрица",
                    "payload": "location_matrica"
                }
            ]
        ]
    ).pack()


# =========================================================
# КНОПКИ ОТЗЫВОВ
# =========================================================

def review_buttons(location):

    if location == "karla":

        yandex = KARLA_YANDEX
        twogis = KARLA_2GIS
        vk = KARLA_VK
        google = KARLA_GOOGLE

        admin_payload = (
            "contact_admin_karla"
        )

    else:

        yandex = MATRICA_YANDEX
        twogis = MATRICA_2GIS
        vk = MATRICA_VK
        google = MATRICA_GOOGLE

        admin_payload = (
            "contact_admin_matrica"
        )

    return ButtonsPayload(
        buttons=[

            [
                {
                    "type": "link",
                    "text": "⭐ Яндекс Карты",
                    "url": yandex
                }
            ],

            [
                {
                    "type": "link",
                    "text": "⭐ 2GIS",
                    "url": twogis
                }
            ],

            [
                {
                    "type": "link",
                    "text": "⭐ ВКонтакте",
                    "url": vk
                }
            ],

            [
                {
                    "type": "link",
                    "text": "⭐ Google",
                    "url": google
                }
            ],

            [
                {
                    "type": "callback",
                    "text": "👨‍💼 Написать Администратору",
                    "payload": admin_payload
                }
            ],

            [
                {
                    "type": "callback",
                    "text": "🔄 Сменить филиал",
                    "payload": "change_location"
                }
            ]

        ]
    ).pack()


# =========================================================
# СПРОСИТЬ ФИЛИАЛ
# =========================================================

async def ask_location(event):

    await event.message.answer(

        "📍 Где вы отдыхали?\n\n"
        "Пожалуйста, выберите филиал:",

        attachments=[
            location_buttons()
        ]
    )


# =========================================================
# МЕНЮ ОТЗЫВОВ
# =========================================================

async def show_reviews(
    event,
    user_id,
    location
):

    if location == "karla":

        location_name = (
            "Карла Маркса"
        )

    else:

        location_name = (
            "ТРЦ Матрица"
        )

    await event.message.answer(

        f"📍 Вы выбрали: "
        f"{location_name}\n\n"

        "❤️ Спасибо, что отдыхали у нас!\n\n"

        "Чтобы принять участие "
        "в розыгрыше призов, "
        "оставьте отзыв на одной "
        "из площадок ниже.\n\n"

        "📸 После публикации отзыва "
        "сделайте скриншот и отправьте "
        "его администратору.\n\n"

        "После проверки отзыва "
        "администратор подтвердит "
        "ваше участие."
    )

    await event.message.answer(

        "👇 Выберите площадку, "
        "где хотите оставить отзыв:",

        attachments=[
            review_buttons(location)
        ]
    )


# =========================================================
# КУПОНЫ ПОЛЬЗОВАТЕЛЯ
# =========================================================

def get_coupons(user_id):

    with get_db() as db:

        return db.execute(
            """
            SELECT *
            FROM coupons
            WHERE user_id = ?
            ORDER BY coupon_number DESC
            """,
            (
                user_id,
            )
        ).fetchall()


async def show_my_coupons(
    event,
    user_id
):

    coupons = get_coupons(
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

        expires = datetime.fromisoformat(
            coupon["expires_at"]
        )

        text += (

            "━━━━━━━━━━━━━━━━━━\n\n"

            f"🎟 Купон: "
            f"{coupon['coupon_number']:05d}\n\n"

            f"🎁 Приз:\n"
            f"{coupon['prize']}\n\n"

            f"⏳ Действует до: "
            f"{expires.strftime('%d.%m.%Y')}\n\n"
        )

    await event.message.answer(
        text
    )


# =========================================================
# ПОЛУЧИТЬ РЕАЛЬНОГО ПОЛЬЗОВАТЕЛЯ CALLBACK
# =========================================================

def get_callback_user(event):

    callback = getattr(
        event,
        "callback",
        None
    )

    if callback is None:

        return None

    user = getattr(
        callback,
        "user",
        None
    )

    return user


# =========================================================
# УВЕДОМЛЕНИЕ АДМИНИСТРАТОРУ
# =========================================================

async def notify_admin(
    admin_id,
    user,
    location_name
):

    # -----------------------------------------------------
    # ID РЕАЛЬНОГО КЛИЕНТА
    # -----------------------------------------------------

    user_id = user.user_id

    # -----------------------------------------------------
    # ИМЯ
    # -----------------------------------------------------

    first_name = (
        getattr(
            user,
            "first_name",
            None
        )
        or "Без имени"
    )

    last_name = (
        getattr(
            user,
            "last_name",
            None
        )
        or ""
    )

    username = (
        getattr(
            user,
            "username",
            None
        )
        or ""
    )

    full_name = (
        f"{first_name} {last_name}"
    ).strip()

    # =====================================================
    # ВАЖНО!
    #
    # НЕ МЕНЯЕМ ЭТОТ ФОРМАТ.
    #
    # Именно такой вариант должен передаваться MAX:
    #
    # [Catharsis](max://user/277114915)
    #
    # Без обратного слеша перед скобками.
    # =====================================================

    profile_link = (
        f"[{full_name}](max://user/{user_id})"
    )

    # =====================================================
    # ТЕКСТ
    # =====================================================

    admin_text = (

        "📨 НОВЫЙ ЗАПРОС АДМИНИСТРАТОРУ\n\n"

        f"📍 Филиал: {location_name}\n\n"

        f"👤 Пользователь: "
        f"{profile_link}\n\n"

        f"🆔 ID пользователя: "
        f"{user_id}\n\n"

        "Пользователь нажал кнопку "
        "«Написать Администратору».\n\n"

        "👉 Нажмите на имя пользователя "
        "выше, чтобы открыть его профиль "
        "в MAX и попробовать написать ему."
    )

    # -----------------------------------------------------
    # USERNAME
    # -----------------------------------------------------

    if username:

        admin_text += (
            f"\n\n🔗 Username: @{username}"
        )

    # -----------------------------------------------------
    # ОТПРАВЛЯЕМ АДМИНУ
    # -----------------------------------------------------

    await bot.send_message(

        user_id=admin_id,

        text=admin_text
    )

    logging.info(

        f"Уведомление отправлено "
        f"администратору {admin_id} "

        f"по пользователю {user_id}"
    )


# =========================================================
# CALLBACK
# =========================================================

@dp.message_callback()
async def callback_handler(event):

    logging.info(
        "Получено callback-событие"
    )

    # -----------------------------------------------------
    # PAYLOAD
    # -----------------------------------------------------

    payload = None

    callback = getattr(
        event,
        "callback",
        None
    )

    if callback is not None:

        payload = getattr(
            callback,
            "payload",
            None
        )

    if payload is None:

        payload = getattr(
            event,
            "payload",
            None
        )

    logging.info(
        f"CALLBACK PAYLOAD: {payload}"
    )

    # -----------------------------------------------------
    # РЕАЛЬНЫЙ ПОЛЬЗОВАТЕЛЬ
    # -----------------------------------------------------

    user = get_callback_user(
        event
    )

    if user is None:

        logging.error(
            "Не удалось определить "
            "реального пользователя callback."
        )

        return

    user_id = user.user_id

    logging.info(

        f"CALLBACK REAL USER: "
        f"{user_id} | "
        f"{getattr(user, 'first_name', '')}"
    )

    # =====================================================
    # СМЕНА ФИЛИАЛА
    # =====================================================

    if payload == "change_location":

        logging.info(

            f"Пользователь {user_id} "
            f"открывает выбор филиала"
        )

        await event.message.answer(

            "🔄 СМЕНА ФИЛИАЛА\n\n"

            "Выберите филиал, "
            "который хотите установить:\n\n"

            "После выбора новый филиал "
            "будет сохранён.",

            attachments=[
                location_buttons()
            ]
        )

        return

    # =====================================================
    # КАРЛА МАРКСА
    # =====================================================

    if payload == "location_karla":

        logging.info(

            f"Пользователь {user_id} "
            f"выбрал Карла Маркса"
        )

        save_location(
            user_id,
            "karla"
        )

        await show_reviews(
            event,
            user_id,
            "karla"
        )

        return

    # =====================================================
    # МАТРИЦА
    # =====================================================

    if payload == "location_matrica":

        logging.info(

            f"Пользователь {user_id} "
            f"выбрал ТРЦ Матрица"
        )

        save_location(
            user_id,
            "matrica"
        )

        await show_reviews(
            event,
            user_id,
            "matrica"
        )

        return

    # =====================================================
    # АДМИНИСТРАТОР — КАРЛА МАРКСА
    # =====================================================

    if payload == "contact_admin_karla":

        logging.info(

            f"Пользователь {user_id} "
            f"хочет связаться "
            f"с администратором Карла Маркса"
        )

        try:

            await notify_admin(

                ADMIN_KARLA_ID,

                user,

                "Карла Маркса"
            )

            await event.message.answer(

                "👨‍💼 Запрос отправлен "
                "администратору филиала "
                "Карла Маркса.\n\n"

                "Администратор свяжется "
                "с вами в MAX."
            )

        except Exception as e:

            logging.exception(
                "Ошибка отправки "
                "уведомления админу Карла Маркса"
            )

            await event.message.answer(

                "❌ Не удалось отправить "
                "запрос администратору.\n\n"

                "Попробуйте ещё раз "
                "немного позже."
            )

        return

    # =====================================================
    # АДМИНИСТРАТОР — МАТРИЦА
    # =====================================================

    if payload == "contact_admin_matrica":

        logging.info(

            f"Пользователь {user_id} "
            f"хочет связаться "
            f"с администратором Матрицы"
        )

        try:

            await notify_admin(

                ADMIN_MATRICA_ID,

                user,

                "ТРЦ Матрица"
            )

            await event.message.answer(

                "👨‍💼 Запрос отправлен "
                "администратору филиала "
                "ТРЦ Матрица.\n\n"

                "Администратор свяжется "
                "с вами в MAX."
            )

        except Exception as e:

            logging.exception(
                "Ошибка отправки "
                "уведомления админу Матрицы"
            )

            await event.message.answer(

                "❌ Не удалось отправить "
                "запрос администратору.\n\n"

                "Попробуйте ещё раз "
                "немного позже."
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

    # =====================================================
    # НЕИЗВЕСТНЫЙ CALLBACK
    # =====================================================

    logging.warning(
        f"Неизвестный callback: {payload}"
    )


# =========================================================
# /USERS
# =========================================================

async def users_command(event):

    user_id = (
        event.message.sender.user_id
    )

    if user_id not in ADMIN_IDS:

        await event.message.answer(
            "❌ У вас нет доступа."
        )

        return

    with get_db() as db:

        users_count = db.execute(
            """
            SELECT COUNT(*)
            FROM users
            """
        ).fetchone()[0]

        coupons_count = db.execute(
            """
            SELECT COUNT(*)
            FROM coupons
            """
        ).fetchone()[0]

        karla_count = db.execute(
            """
            SELECT COUNT(*)
            FROM users
            WHERE location = 'karla'
            """
        ).fetchone()[0]

        matrica_count = db.execute(
            """
            SELECT COUNT(*)
            FROM users
            WHERE location = 'matrica'
            """
        ).fetchone()[0]

    await event.message.answer(

        "👑 СТАТИСТИКА\n\n"

        f"👥 Участников: "
        f"{users_count}\n"

        f"🎟 Купонов: "
        f"{coupons_count}\n\n"

        "📍 ФИЛИАЛЫ\n\n"

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
    user_id,
    phone
):

    if not is_phone(phone):

        await event.message.answer(

            "❌ Не удалось распознать номер.\n\n"

            "Попробуйте поделиться "
            "номером ещё раз."
        )

        return

    phone = normalize_phone(
        phone
    )

    # =====================================================
    # ПОЛЬЗОВАТЕЛЬ УЖЕ СУЩЕСТВУЕТ
    # =====================================================

    existing = get_user(
        user_id
    )

    if existing:

        waiting_phone.discard(
            user_id
        )

        logging.info(

            f"Пользователь {user_id} "
            f"уже есть в базе. "
            f"Повторная регистрация отменена."
        )

        if existing["location"]:

            await show_reviews(

                event,

                user_id,

                existing["location"]
            )

        else:

            await ask_location(
                event
            )

        return

    # =====================================================
    # ТЕЛЕФОН УЖЕ ИСПОЛЬЗОВАЛСЯ
    # =====================================================

    phone_owner = get_user_by_phone(
        phone
    )

    if phone_owner:

        waiting_phone.discard(
            user_id
        )

        await event.message.answer(

            "❌ Этот номер телефона уже "
            "использовался для получения "
            "купона."
        )

        return

    # =====================================================
    # СОЗДАЁМ ПОЛЬЗОВАТЕЛЯ
    # =====================================================

    try:

        create_user(
            user_id,
            phone
        )

    except sqlite3.IntegrityError:

        logging.exception(
            "Ошибка добавления пользователя"
        )

        await event.message.answer(

            "❌ Не удалось зарегистрировать "
            "пользователя. Попробуйте ещё раз."
        )

        return

    # =====================================================
    # ВАЖНО:
    # Пользователь больше НЕ ждёт телефон
    # =====================================================

    waiting_phone.discard(
        user_id
    )

    logging.info(

        f"Пользователь {user_id} "
        f"успешно зарегистрирован."
    )

    # =====================================================
    # СОЗДАЁМ КУПОН
    # =====================================================

    try:

        (
            coupon_number,
            prize,
            created_at,
            expires_at
        ) = create_coupon(
            user_id
        )

    except Exception:

        logging.exception(
            "Ошибка создания купона"
        )

        await event.message.answer(

            "❌ Произошла ошибка "
            "при создании купона.\n\n"

            "Обратитесь к администратору."
        )

        return

    # =====================================================
    # ОТПРАВЛЯЕМ КУПОН
    # =====================================================

    await event.message.answer(

        "🎉 ПОЗДРАВЛЯЕМ!\n\n"

        "Вы получили новый купон! 🎁\n\n"

        f"🎟 НОМЕР КУПОНА:\n"
        f"{coupon_number:05d}\n\n"

        f"🎁 ВАШ ПРИЗ:\n"
        f"{prize}\n\n"

        f"⏳ Действует до: "
        f"{expires_at.strftime('%d.%m.%Y')}\n\n"

        "Покажите это сообщение "
        "администратору или сделайте "
        "скриншот."
    )

    # =====================================================
    # ПОСЛЕ КУПОНА — ФИЛИАЛ
    # =====================================================

    await ask_location(
        event
    )


# =========================================================
# ОСНОВНОЙ ОБРАБОТЧИК
# =========================================================

@dp.message_created()
async def messages(
    event: MessageCreated
):

    user = event.message.sender

    user_id = user.user_id

    text = (

        getattr(
            event.message.body,
            "text",
            None
        )

        or ""
    ).strip()

    logging.info(

        f"MESSAGE: user_id={user_id}, "
        f"text={text!r}"
    )

    # =====================================================
    # /USERS
    # =====================================================

    if text.lower() == "/users":

        await users_command(
            event
        )

        return

    # =====================================================
    # КОНТАКТ
    # =====================================================

    phone = get_phone_from_event(
        event
    )

    if phone:

        logging.info(

            f"Получен телефон "
            f"user_id={user_id}"
        )

        await process_phone(

            event,

            user_id,

            phone
        )

        return

    # =====================================================
    # ПРОВЕРКА:
    # ПОЛЬЗОВАТЕЛЬ УЖЕ ЗАРЕГИСТРИРОВАН?
    # =====================================================

    existing_user = get_user(
        user_id
    )

    if existing_user:

        # -------------------------------------------------
        # Удаляем из временного ожидания,
        # если вдруг он там остался.
        # -------------------------------------------------

        waiting_phone.discard(
            user_id
        )

        logging.info(

            f"Пользователь {user_id} "
            f"уже зарегистрирован."
        )

        # -------------------------------------------------
        # ФИЛИАЛ УЖЕ ВЫБРАН
        # -------------------------------------------------

        if existing_user["location"]:

            location_name = (
                "Карла Маркса"
                if existing_user["location"] == "karla"
                else "ТРЦ Матрица"
            )

            await event.message.answer(

                "👋 Вы уже зарегистрированы!\n\n"

                f"📍 Текущий филиал: "
                f"{location_name}\n\n"

                "Выберите нужное действие:",

                attachments=[
                    review_buttons(
                        existing_user["location"]
                    )
                ]
            )

        # -------------------------------------------------
        # ФИЛИАЛ ЕЩЁ НЕ ВЫБРАН
        # -------------------------------------------------

        else:

            await ask_location(
                event
            )

        return

    # =====================================================
    # НОВЫЙ ПОЛЬЗОВАТЕЛЬ
    # =====================================================

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

    # =====================================================
    # ПЕРВОЕ СООБЩЕНИЕ
    # =====================================================

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
            f"здравствуйте! 👋\n\n"

            "Вы нашли секретный подарок! 🎁\n\n"

            "Чтобы получить подарок, "
            "подтвердите свой номер телефона.\n\n"

            "Нажмите кнопку ниже "
            "и поделитесь номером."
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
