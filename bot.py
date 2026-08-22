import asyncio
import logging
import random
import re
import sqlite3
from calendar import monthrange
from datetime import datetime, timezone

from maxapi import Bot, Dispatcher
from maxapi.types import (
    MessageCreated,
    MessageCallback,
    ButtonsPayload,
    RequestContactButton,
    CallbackButton,
    LinkButton,
)


# =========================================================
# НАСТРОЙКИ
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)


# =========================================================
# ТОКЕН
# =========================================================

TOKEN = "f9LHodD0cOLJZ_QQj9kIYtnBMD3eCbHBwsf0UQWM34VCwzIwHu7wFVCjZ47aEkfWXziwgMn1oScOGgBlLoF5"


# =========================================================
# АДМИНИСТРАТОРЫ
# =========================================================

ADMIN_IDS = {
    277114915
}

# MAX user_id администратора
ADMIN_USER_ID = 174516690


# =========================================================
# DATABASE
# =========================================================

DB_NAME = "users.db"


# =========================================================
# ВРЕМЕННЫЕ СОСТОЯНИЯ
# =========================================================

waiting_phone = set()

waiting_location = set()

# user_id -> "karla" / "matrix"
user_locations = {}


# =========================================================
# ПРИЗЫ
# =========================================================

# Все призы равновероятны.
#
# Дубли убраны.

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
# ФИЛИАЛЫ
# =========================================================

LOCATIONS = {

    "karla": {
        "name": "Карла Маркса",

        "yandex": (
            "https://yandex.ru/maps/org/vr_connect/"
            "18951109146/?add-review=true&"
            "ll=53.201618%2C56.859488&z=16"
        ),

        "2gis": (
            "https://2gis.ru/izhevsk/firm/"
            "70000001050199074/tab/reviews/addreview?"
            "m=53.201516%2C56.85975%2F16"
        ),

        "vk": (
            "https://vk.ru/reviews-202166323"
        ),

        "google": (
            "https://www.google.com/search?"
            "q=vr+connect&oq=vr+connect+&"
            "gs_lcrp=EgZjaHJvbWUyCggAEEUYFhgeGDky"
            "DwgBEC4YJxivARjHARiOBTIGCAIQIxgnMgcIAxAAGIAEM"
            "ggIBBAAGBYYHjIGCAUQRRg8MgYIBhBFGD0yBggHEEUYPdIBC"
            "DE1NDNqMGo3qAIAsAIA&sourceid=chrome&"
            "source=chrome.ob&ie=UTF-8#lrd=0x43e139a639bba375:"
            "0x6a6865f0dd058151,3,,,,"
        ),
    },

    "matrix": {
        "name": "ТРЦ Матрица",

        "yandex": (
            "https://yandex.ru/maps/org/vr_connect/"
            "36851840813/reviews/?add-review=true&"
            "indoorLevel=1&ll=53.124389%2C56.832935&"
            "tab=reviews&z=16.98"
        ),

        "2gis": (
            "https://2gis.ru/izhevsk/search/"
            "vr-%D0%B0%D1%80%D0%B5%D0%BD%D0%B0%20Connect/"
            "firm/70000001114081013/"
            "53.125482%2C56.832989/tab/reviews/"
            "addreview?m=53.163537%2C56.846359%2F14.26"
        ),

        "vk": (
            "https://vk.ru/reviews-202166323"
        ),

        "google": (
            "https://www.google.com/search?"
            "q=vr+connect&oq=vr+connect+&"
            "gs_lcrp=EgZjaHJvbWUyCggAEEUYFhgeGDky"
            "DwgBEC4YJxivARjHARiOBTIGCAIQIxgnMgcIAxAAGIAEM"
            "ggIBBAAGBYYHjIGCAUQRRg8MgYIBhBFGD0yBggHEEUYPdIBC"
            "DE1NDNqMGo3qAIAsAIA&sourceid=chrome&"
            "source=chrome.ob&ie=UTF-8#lrd=0x43e139a639bba375:"
            "0x6a6865f0dd058151,3,,,,"
        ),
    },
}


# =========================================================
# BOT
# =========================================================

bot = Bot(TOKEN)

dp = Dispatcher()


# =========================================================
# DATABASE
# =========================================================

def get_db():

    connection = sqlite3.connect(
        DB_NAME
    )

    connection.row_factory = sqlite3.Row

    return connection


def add_column_if_missing(
    db,
    table,
    column,
    definition
):

    columns = db.execute(
        f"PRAGMA table_info({table})"
    ).fetchall()

    existing_columns = {
        row["name"]
        for row in columns
    }

    if column not in existing_columns:

        db.execute(
            f"""
            ALTER TABLE {table}
            ADD COLUMN {column} {definition}
            """
        )

        logging.info(
            "Добавлена колонка %s",
            column
        )


def init_db():

    with get_db() as db:

        db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                user_id INTEGER NOT NULL,

                phone TEXT NOT NULL,

                coupon TEXT NOT NULL UNIQUE,

                prize TEXT,

                created_at TEXT,

                expires_at TEXT
            )
            """
        )

        add_column_if_missing(
            db,
            "users",
            "prize",
            "TEXT"
        )

        add_column_if_missing(
            db,
            "users",
            "created_at",
            "TEXT"
        )

        add_column_if_missing(
            db,
            "users",
            "expires_at",
            "TEXT"
        )

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

    logging.info(
        "База данных инициализирована."
    )


# =========================================================
# DATABASE — ПОЛЬЗОВАТЕЛИ
# =========================================================

def get_user(user_id):

    with get_db() as db:

        cursor = db.execute(
            """
            SELECT *
            FROM users
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (user_id,)
        )

        return cursor.fetchone()


def get_user_by_phone(phone):

    with get_db() as db:

        cursor = db.execute(
            """
            SELECT *
            FROM users
            WHERE phone = ?
            ORDER BY id ASC
            LIMIT 1
            """,
            (phone,)
        )

        return cursor.fetchone()


def get_user_coupons(user_id):

    with get_db() as db:

        cursor = db.execute(
            """
            SELECT *
            FROM users
            WHERE user_id = ?
            ORDER BY id ASC
            """,
            (user_id,)
        )

        return cursor.fetchall()


def get_users_count():

    with get_db() as db:

        cursor = db.execute(
            """
            SELECT COUNT(DISTINCT user_id)
            FROM users
            """
        )

        return cursor.fetchone()[0]


# =========================================================
# НОМЕР КУПОНА
# =========================================================

def get_next_coupon_number():

    with get_db() as db:

        rows = db.execute(
            """
            SELECT coupon
            FROM users
            """
        ).fetchall()

    # До этого было выдано 01267.
    # Следующий должен быть 01268.

    max_number = 1267

    for row in rows:

        coupon = row["coupon"]

        if not coupon:
            continue

        digits = re.sub(
            r"\D",
            "",
            str(coupon)
        )

        if not digits:
            continue

        try:

            number = int(digits)

            if number > max_number:
                max_number = number

        except ValueError:

            pass

    return max_number + 1


def generate_coupon():

    number = get_next_coupon_number()

    return str(number).zfill(5)


# =========================================================
# ДАТА + 1 МЕСЯЦ
# =========================================================

def add_one_month(dt):

    year = dt.year

    month = dt.month + 1

    if month > 12:

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

def create_coupon(
    user_id,
    phone,
    prize
):

    coupon = generate_coupon()

    created_at = datetime.now(
        timezone.utc
    )

    expires_at = add_one_month(
        created_at
    )

    with get_db() as db:

        db.execute(
            """
            INSERT INTO users (
                user_id,
                phone,
                coupon,
                prize,
                created_at,
                expires_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                phone,
                coupon,
                prize,
                created_at.isoformat(),
                expires_at.isoformat()
            )
        )

        db.commit()

    return coupon, expires_at


# =========================================================
# PHONE
# =========================================================

def normalize_phone(phone):

    digits = re.sub(
        r"\D",
        "",
        str(phone)
    )

    if (
        digits.startswith("8")
        and len(digits) == 11
    ):

        digits = (
            "7"
            + digits[1:]
        )

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

                    return match.group(1).strip()

    except Exception as e:

        logging.exception(
            "Ошибка получения телефона: %s",
            e
        )

    return None


# =========================================================
# КНОПКИ — ФИЛИАЛЫ
# =========================================================

def make_location_buttons():

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
                    payload="location_matrix"
                )
            ]
        ]
    )

    return buttons.pack()


# =========================================================
# КНОПКИ — ОТЗЫВЫ
# =========================================================

def make_review_buttons(location):

    data = LOCATIONS[location]

    buttons = ButtonsPayload(
        buttons=[
            [
                LinkButton(
                    text="⭐ Яндекс",
                    url=data["yandex"]
                )
            ],
            [
                LinkButton(
                    text="⭐ 2GIS",
                    url=data["2gis"]
                )
            ],
            [
                LinkButton(
                    text="⭐ VK",
                    url=data["vk"]
                )
            ],
            [
                LinkButton(
                    text="⭐ Google",
                    url=data["google"]
                )
            ],
            [
                CallbackButton(
                    text="📸 Как подтвердить отзыв?",
                    payload="review_help"
                )
            ],
            [
                LinkButton(
                    text="👨‍💼 Написать администратору",
                    url=f"max://user/{ADMIN_USER_ID}"
                )
            ]
        ]
    )

    return buttons.pack()


# =========================================================
# КНОПКИ — ПОМОЩЬ
# =========================================================

def make_review_help_buttons():

    buttons = ButtonsPayload(
        buttons=[
            [
                LinkButton(
                    text="👨‍💼 Отправить скриншот",
                    url=f"max://user/{ADMIN_USER_ID}"
                )
            ],
            [
                CallbackButton(
                    text="⬅️ Вернуться к площадкам",
                    payload="back_reviews"
                )
            ]
        ]
    )

    return buttons.pack()


# =========================================================
# МЕНЮ ФИЛИАЛА
# =========================================================

async def show_location_menu(
    event,
    user_id
):

    waiting_location.add(
        user_id
    )

    await event.message.answer(
        text=(
            "📍 Где вы отдыхали?\n\n"

            "Выберите филиал, который вы посещали:"
        ),
        attachments=[
            make_location_buttons()
        ]
    )


# =========================================================
# МЕНЮ ОТЗЫВОВ
# =========================================================

async def show_review_menu(
    event,
    user_id
):

    location = user_locations.get(
        user_id
    )

    if location is None:

        await show_location_menu(
            event,
            user_id
        )

        return

    location_name = LOCATIONS[
        location
    ]["name"]

    await event.message.answer(
        text=(
            f"⭐ Отзывы — {location_name}\n\n"

            "Выберите площадку, на которой "
            "хотите оставить отзыв:\n\n"

            "📸 ВАЖНО!\n\n"

            "После публикации отзыва обязательно "
            "сделайте скриншот и отправьте его "
            "администратору.\n\n"

            "Это необходимо для подтверждения "
            "отзыва и получения крутки барабана. 🎰\n\n"

            "Выберите площадку:"
        ),
        attachments=[
            make_review_buttons(
                location
            )
        ]
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
            "❌ Не удалось распознать номер телефона.\n\n"
            "Попробуйте поделиться номером ещё раз."
        )

        return

    phone = normalize_phone(
        phone
    )

    # =====================================================
    # ЭТОТ НОМЕР УЖЕ ИСПОЛЬЗОВАЛСЯ?
    #
    # Тогда новый купон НЕ создаём.
    # =====================================================

    existing = get_user_by_phone(
        phone
    )

    if existing:

        waiting_phone.discard(
            user_id
        )

        await event.message.answer(
            "🎟 Этот номер телефона уже "
            "использовался для получения купона.\n\n"

            f"Ваш купон №{existing['coupon']}\n\n"

            f"🎁 Приз:\n"
            f"{existing['prize'] or 'не указан'}\n\n"

            "Новый купон по этому номеру "
            "создаваться не будет."
        )

        await show_location_menu(
            event,
            user_id
        )

        return

    # =====================================================
    # НОВЫЙ КУПОН
    # =====================================================

    prize = random.choice(
        PRIZES
    )

    try:

        coupon, expires_at = create_coupon(
            user_id=user_id,
            phone=phone,
            prize=prize
        )

    except sqlite3.IntegrityError as e:

        logging.exception(
            "Ошибка создания купона: %s",
            e
        )

        await event.message.answer(
            "❌ Не удалось создать купон.\n\n"
            "Попробуйте ещё раз."
        )

        return

    waiting_phone.discard(
        user_id
    )

    expires_text = expires_at.strftime(
        "%d.%m.%Y"
    )

    logging.info(
        "Новый купон: user_id=%s coupon=%s prize=%s",
        user_id,
        coupon,
        prize
    )

    # =====================================================
    # ВЫДАЁМ КУПОН
    # =====================================================

    await event.message.answer(
        text=(
            "🎉 ПОЗДРАВЛЯЕМ!\n\n"

            f"🎟 Ваш купон №{coupon}\n\n"

            f"🎁 Ваш приз:\n"
            f"{prize}\n\n"

            f"⏳ Купон действует до "
            f"{expires_text}.\n\n"

            "Сохраните это сообщение "
            "или сделайте скриншот."
        )
    )

    # =====================================================
    # СПРАШИВАЕМ ФИЛИАЛ
    # =====================================================

    await show_location_menu(
        event,
        user_id
    )


# =========================================================
# MESSAGE CREATED
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
        "MESSAGE: user_id=%s text=%r",
        user_id,
        text
    )

    # =====================================================
    # /users
    # =====================================================

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

    # =====================================================
    # КОНТАКТ
    # =====================================================

    phone = get_phone_from_event(
        event
    )

    if phone:

        logging.info(
            "PHONE: user_id=%s phone=%s",
            user_id,
            phone
        )

        await process_phone(
            event,
            user_id,
            phone
        )

        return

    # =====================================================
    # ЖДЁМ ТЕЛЕФОН
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
                "❌ Это не похоже на номер телефона.\n\n"

                "Нажмите кнопку "
                "«📱 Поделиться номером» "
                "или отправьте номер вручную.\n\n"

                "Например:\n"
                "89991234567"
            )

        return

    # =====================================================
    # ЕСЛИ ЖДЁМ ФИЛИАЛ
    # =====================================================

    if user_id in waiting_location:

        await event.message.answer(
            "📍 Пожалуйста, выберите филиал "
            "одной из кнопок выше."
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
            f"{first_name}, здравствуйте! 👋\n\n"

            "Вы нашли секретный подарок! 🎁\n\n"

            "Чтобы он стал вашим, бот должен "
            "убедиться, что вы — реальный человек.\n\n"

            "Для подтверждения нажмите кнопку ниже "
            "и поделитесь своим номером телефона.\n\n"

            "Или можете отправить номер вручную."
        ),
        attachments=[
            buttons
        ]
    )


# =========================================================
# CALLBACK
# =========================================================

@dp.message_callback()
async def callbacks(
    event: MessageCallback
):

    try:

        # =================================================
        # PAYLOAD
        # =================================================

        payload = event.callback.payload

        # =================================================
        # USER ID
        # =================================================

        user_id = event.callback.user.user_id

        logging.info(
            "CALLBACK: user_id=%s payload=%r",
            user_id,
            payload
        )

        # =================================================
        # СРАЗУ ПОДТВЕРЖДАЕМ НАЖАТИЕ
        # =================================================

        try:

            await event.answer()

        except Exception as e:

            logging.warning(
                "Не удалось подтвердить callback: %s",
                e
            )

        # =================================================
        # КАРЛА МАРКСА
        # =================================================

        if payload == "location_karla":

            user_locations[
                user_id
            ] = "karla"

            waiting_location.discard(
                user_id
            )

            logging.info(
                "Выбран филиал Карла Маркса: %s",
                user_id
            )

            await show_review_menu(
                event,
                user_id
            )

            return

        # =================================================
        # ТРЦ МАТРИЦА
        # =================================================

        if payload == "location_matrix":

            user_locations[
                user_id
            ] = "matrix"

            waiting_location.discard(
                user_id
            )

            logging.info(
                "Выбран филиал ТРЦ Матрица: %s",
                user_id
            )

            await show_review_menu(
                event,
                user_id
            )

            return

        # =================================================
        # ПОМОЩЬ
        # =================================================

        if payload == "review_help":

            await event.message.answer(
                text=(
                    "📸 КАК ПОДТВЕРДИТЬ ОТЗЫВ?\n\n"

                    "1️⃣ Выберите площадку — "
                    "Яндекс, 2GIS, VK или Google.\n\n"

                    "2️⃣ Оставьте отзыв о вашем посещении.\n\n"

                    "3️⃣ После публикации сделайте "
                    "скриншот отзыва.\n\n"

                    "4️⃣ Нажмите "
                    "«👨‍💼 Отправить скриншот».\n\n"

                    "5️⃣ Отправьте скриншот "
                    "администратору.\n\n"

                    "✅ Администратор проверит отзыв.\n\n"

                    "🎰 После подтверждения отзыва "
                    "вы получите одну крутку "
                    "барабана призов."
                ),
                attachments=[
                    make_review_help_buttons()
                ]
            )

            return

        # =================================================
        # НАЗАД
        # =================================================

        if payload == "back_reviews":

            await show_review_menu(
                event,
                user_id
            )

            return

        # =================================================
        # НЕИЗВЕСТНЫЙ CALLBACK
        # =================================================

        logging.warning(
            "НЕИЗВЕСТНЫЙ CALLBACK: %r",
            payload
        )

    except Exception as e:

        logging.exception(
            "ОШИБКА CALLBACK: %s",
            e
        )


# =========================================================
# MAIN
# =========================================================

async def main():

    init_db()

    logging.info(
        "Бот запускается..."
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
