import asyncio
import logging
import re
import sqlite3
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta

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

# =========================================================
# ТОКЕН БОТА
# =========================================================

TOKEN = "f9LHodD0cOLJZ_QQj9kIYtnBMD3eCbHBwsf0UQWM34VCwzIwHu7wFVCjZ47aEkfWXziwgMn1oScOGgBlLoF5"

# =========================================================
# АДМИНИСТРАТОРЫ
# =========================================================

ADMIN_IDS = {
    277114915
}

# MAX ID администратора,
# которому пользователь может написать.
ADMIN_USER_ID = 174516690

# =========================================================
# БАЗА
# =========================================================

DB_NAME = "users.db"

# =========================================================
# СОСТОЯНИЯ ПОЛЬЗОВАТЕЛЕЙ
# =========================================================

# Пользователь сейчас должен указать телефон.
waiting_phone = set()

# Пользователь должен выбрать филиал.
waiting_location = set()

# Пользователь уже выбрал филиал.
# Формат:
# {
#     user_id: "karla"
# }
user_locations = {}

# Пользователь сейчас находится в меню отзывов.
review_menu_users = set()


# =========================================================
# ПРИЗЫ
# =========================================================

PRIZES = [
    "1 час игры в VR шлеме",

    "1 час игры на любой консоли",

    "15 минут игры в VR Автосимуляторе",

    "30 минут игры на консоли",

    "1 час в VR шлеме, при аренде от 1 часа VR шлема",

    "1 час игр на консоли (XBox / PS5), при аренде от 1 часа VR шлема",

    "15 минут игр на VR Автосимуляторе, при аренде 15 минут на Автосимуляторе",

    "30 минут игры на консоли (XBox / PS5), при аренде от 1 часа VR шлема",

    "Бонус 500 ₽ при покупке сертификата от 1000 ₽",

    "Скидка 500 ₽ на покупку любого абонемента",

    "Скидка 500 ₽ при аренде VR шлема на дом",

    "Скидка 300 ₽ на второй час аренды VR шлема",

    "1 час игр на консоли (XBox / PS5), при аренде от 1 часа аренды консоли",

    "2 часа игры в VR",

    "15 минут игр на автосимуляторе, при аренде от 1 часа VR шлема",
]


# =========================================================
# ССЫЛКИ НА ОТЗЫВЫ
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
    }
}


# =========================================================
# БОТ
# =========================================================

bot = Bot(TOKEN)
dp = Dispatcher()


# =========================================================
# DATABASE
# =========================================================

def get_db():
    connection = sqlite3.connect(DB_NAME)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():

    with get_db() as db:

        db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                user_id INTEGER NOT NULL,

                phone TEXT NOT NULL,

                coupon TEXT NOT NULL UNIQUE,

                prize TEXT NOT NULL,

                created_at TEXT NOT NULL,

                expires_at TEXT NOT NULL
            )
            """
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

    logging.info("База данных инициализирована.")


# =========================================================
# ПОЛЬЗОВАТЕЛИ
# =========================================================

def get_user(user_id: int):

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


def get_user_by_phone(phone: str):

    with get_db() as db:

        cursor = db.execute(
            """
            SELECT *
            FROM users
            WHERE phone = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (phone,)
        )

        return cursor.fetchone()


def get_users_count() -> int:

    with get_db() as db:

        cursor = db.execute(
            """
            SELECT COUNT(DISTINCT user_id)
            FROM users
            """
        )

        return cursor.fetchone()[0]


def get_user_coupons(user_id: int):

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


# =========================================================
# НОМЕР КУПОНА
# =========================================================

def get_next_coupon_number():

    with get_db() as db:

        cursor = db.execute(
            """
            SELECT coupon
            FROM users
            ORDER BY id DESC
            LIMIT 1
            """
        )

        row = cursor.fetchone()

        # Если база пустая — начинаем с 01268.
        if row is None:
            return 1268

        last_coupon = row["coupon"]

        # Берём только цифры.
        digits = re.sub(r"\D", "", last_coupon)

        if not digits:
            return 1268

        return int(digits) + 1


def generate_coupon():

    number = get_next_coupon_number()

    return str(number).zfill(5)


# =========================================================
# СОЗДАНИЕ ПОЛЬЗОВАТЕЛЯ / КУПОНА
# =========================================================

def create_coupon(
    user_id: int,
    phone: str,
    prize: str
):

    coupon = generate_coupon()

    created_at = datetime.now(timezone.utc)

    # Срок действия — 1 месяц.
    expires_at = created_at + relativedelta(months=1)

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

def normalize_phone(phone: str):

    digits = re.sub(r"\D", "", phone)

    if digits.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]

    return digits


def is_phone(phone: str):

    digits = normalize_phone(phone)

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
            f"Ошибка получения телефона: {e}"
        )

    return None


# =========================================================
# КНОПКИ
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
                    "payload": "location_matrix"
                }
            ]
        ]
    ).pack()


def review_buttons(location):

    data = LOCATIONS[location]

    return ButtonsPayload(
        buttons=[
            [
                {
                    "type": "url",
                    "text": "⭐ Яндекс",
                    "url": data["yandex"]
                }
            ],
            [
                {
                    "type": "url",
                    "text": "⭐ 2GIS",
                    "url": data["2gis"]
                }
            ],
            [
                {
                    "type": "url",
                    "text": "⭐ VK",
                    "url": data["vk"]
                }
            ],
            [
                {
                    "type": "url",
                    "text": "⭐ Google",
                    "url": data["google"]
                }
            ],
            [
                {
                    "type": "callback",
                    "text": "📸 Как подтвердить отзыв?",
                    "payload": "review_help"
                }
            ],
            [
                {
                    "type": "url",
                    "text": "👨‍💼 Написать администратору",
                    "url": f"max://user/{ADMIN_USER_ID}"
                }
            ]
        ]
    ).pack()


def after_review_buttons():

    return ButtonsPayload(
        buttons=[
            [
                {
                    "type": "url",
                    "text": "👨‍💼 Отправить скриншот администратору",
                    "url": f"max://user/{ADMIN_USER_ID}"
                }
            ],
            [
                {
                    "type": "callback",
                    "text": "⭐ Вернуться к отзывам",
                    "payload": "back_reviews"
                }
            ]
        ]
    ).pack()


# =========================================================
# ВЫДАЧА КУПОНА
# =========================================================

async def process_phone(
    event,
    user_id: int,
    phone: str
):

    if not is_phone(phone):

        await event.message.answer(
            "❌ Не удалось распознать номер телефона.\n\n"
            "Попробуйте поделиться номером ещё раз."
        )

        return

    phone = normalize_phone(phone)

    # -----------------------------------------------------
    # Проверяем телефон.
    # Один номер = один первый купон.
    # -----------------------------------------------------

    existing_phone = get_user_by_phone(phone)

    if existing_phone:

        waiting_phone.discard(user_id)

        await event.message.answer(
            "🎟 Этот номер телефона уже использовался "
            "для получения купона.\n\n"
            f"Ваш купон:\n\n"
            f"🎁 №{existing_phone['coupon']}\n\n"
            f"Приз:\n"
            f"{existing_phone['prize']}\n\n"
            "Если вы хотите посмотреть все свои купоны, "
            "используйте кнопку «Мои купоны»."
        )

        # Показываем меню филиалов/отзывов.
        waiting_location.add(user_id)

        await event.message.answer(
            "📍 Где вы отдыхали?",
            attachments=[
                location_buttons()
            ]
        )

        return

    # -----------------------------------------------------
    # Новый купон
    # -----------------------------------------------------

    # Равновероятный выбор приза.
    import random

    prize = random.choice(PRIZES)

    try:

        coupon, expires_at = create_coupon(
            user_id=user_id,
            phone=phone,
            prize=prize
        )

    except sqlite3.IntegrityError:

        logging.exception(
            "Ошибка создания купона."
        )

        await event.message.answer(
            "❌ Произошла ошибка при выдаче купона.\n"
            "Попробуйте ещё раз."
        )

        return

    waiting_phone.discard(user_id)

    logging.info(
        f"Новый купон: "
        f"user_id={user_id}, "
        f"phone={phone}, "
        f"coupon={coupon}, "
        f"prize={prize}"
    )

    expires_text = expires_at.strftime(
        "%d.%m.%Y"
    )

    await event.message.answer(
        "🎉 ПОЗДРАВЛЯЕМ!\n\n"
        f"🎟 Ваш купон №{coupon}\n\n"
        f"🎁 Ваш приз:\n"
        f"{prize}\n\n"
        f"⏳ Купон действует до {expires_text}.\n\n"
        "Сохраните это сообщение или сделайте "
        "скриншот — он понадобится при использовании "
        "купона."
    )

    # -----------------------------------------------------
    # Переходим к филиалу
    # -----------------------------------------------------

    waiting_location.add(user_id)

    await event.message.answer(
        "📍 Где вы отдыхали?\n\n"
        "Выберите филиал, который вы посещали:",
        attachments=[
            location_buttons()
        ]
    )


# =========================================================
# МЕНЮ ОТЗЫВОВ
# =========================================================

async def show_reviews(event, user_id):

    location = user_locations.get(user_id)

    if not location:
        return

    location_name = LOCATIONS[location]["name"]

    review_menu_users.add(user_id)

    await event.message.answer(
        f"⭐ Отзыв о посещении — {location_name}\n\n"
        "Оставьте отзыв на одной из площадок ниже.\n\n"
        "📸 ВАЖНО!\n\n"
        "Чтобы подтвердить отзыв и получить "
        "возможность испытать удачу в барабане 🎰, "
        "после публикации отзыва сделайте скриншот "
        "и отправьте его администратору.\n\n"
        "Выберите площадку:",
        attachments=[
            review_buttons(location)
        ]
    )


# =========================================================
# MESSAGES
# =========================================================

@dp.message_created()
async def messages(event: MessageCreated):

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
    # CONTACT
    # =====================================================

    phone = get_phone_from_event(event)

    if phone:

        await process_phone(
            event,
            user_id,
            phone
        )

        return

    # =====================================================
    # CALLBACK
    #
    # В разных версиях maxapi callback может приходить
    # немного по-разному. Поэтому ниже максимально
    # безопасно пытаемся получить payload.
    # =====================================================

    payload = getattr(
        event,
        "callback",
        None
    )

    if payload is None:
        payload = getattr(
            event,
            "payload",
            None
        )

    if payload is not None:

        callback_payload = getattr(
            payload,
            "payload",
            None
        )

        if callback_payload is None:

            callback_payload = getattr(
                payload,
                "callback_data",
                None
            )

        if callback_payload is None:

            callback_payload = str(payload)

        # -------------------------------------------------
        # КАРЛА МАРКСА
        # -------------------------------------------------

        if "location_karla" in callback_payload:

            user_locations[user_id] = "karla"

            waiting_location.discard(user_id)

            await show_reviews(
                event,
                user_id
            )

            return

        # -------------------------------------------------
        # МАТРИЦА
        # -------------------------------------------------

        if "location_matrix" in callback_payload:

            user_locations[user_id] = "matrix"

            waiting_location.discard(user_id)

            await show_reviews(
                event,
                user_id
            )

            return

        # -------------------------------------------------
        # ПОМОЩЬ ПО ОТЗЫВУ
        # -------------------------------------------------

        if "review_help" in callback_payload:

            await event.message.answer(
                "📸 Как подтвердить отзыв\n\n"
                "1️⃣ Выберите любую площадку выше.\n\n"
                "2️⃣ Оставьте отзыв о вашем посещении.\n\n"
                "3️⃣ После публикации сделайте "
                "скриншот отзыва.\n\n"
                "4️⃣ Отправьте скриншот администратору.\n\n"
                "5️⃣ Администратор проверит отзыв "
                "и подтвердит вашу крутку 🎰.\n\n"
                "❤️ Один подтверждённый отзыв = "
                "одна крутка.\n\n"
                "Если вы оставили отзывы на нескольких "
                "площадках, отправьте скриншот каждого "
                "отзыва.",
                attachments=[
                    after_review_buttons()
                ]
            )

            return

        # -------------------------------------------------
        # НАЗАД К ОТЗЫВАМ
        # -------------------------------------------------

        if "back_reviews" in callback_payload:

            await show_reviews(
                event,
                user_id
            )

            return

    # =====================================================
    # ЕСЛИ ЖДЁМ ТЕЛЕФОН
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
            "с помощью кнопки:\n\n"
            "1️⃣ Карла Маркса\n"
            "2️⃣ ТРЦ Матрица"
        )

        return

    # =====================================================
    # ПЕРВОЕ СООБЩЕНИЕ
    # =====================================================

    waiting_phone.add(user_id)

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
# MAIN
# =========================================================

async def main():

    init_db()

    logging.info(
        "Бот запускается..."
    )

    await dp.start_polling(bot)


if __name__ == "__main__":

    asyncio.run(main())
