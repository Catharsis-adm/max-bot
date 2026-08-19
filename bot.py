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

# =========================================================
# ВСТАВЬ СЮДА НОВЫЙ ТОКЕН БОТА
# Старый токен, который был опубликован ранее,
# обязательно перевыпусти.
# =========================================================

TOKEN = "f9LHodD0cOLJZ_QQj9kIYtnBMD3eCbHBwsf0UQWM34VCwzIwHu7wFVCjZ47aEkfWXziwgMn1oScOGgBlLoF5"


# MAX user_id администратора
ADMIN_IDS = {277114915}


# Файл базы
DB_NAME = "users.db"


# =========================================================
# НАСТРОЙКИ КУПОНОВ
# =========================================================

# Последний уже существовавший номер:
# 01267
#
# Поэтому первый новый купон будет:
# 01268
#
INITIAL_COUPON_NUMBER = 1267


# Все призы равновероятны.
# Дубли удалены.
PRIZES = [
    "1 час игры в VR шлеме",

    "1 час игры на любой консоли",

    "15 минут игры в VR Автосимуляторе",

    "30 минут игры на консоли",

    "1 час в VR шлеме, при аренде от 1 часа VR шлема",

    "1 час игр на консоли (XBox / PS5), при аренде от 1 часа VR шлема",

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


# Временное состояние пользователей,
# которым нужно предоставить номер.
waiting_phone = set()


# =========================================================
# DATABASE
# =========================================================

def get_db():
    """
    Открываем SQLite.
    """

    connection = sqlite3.connect(DB_NAME)

    connection.row_factory = sqlite3.Row

    return connection


def init_db():
    """
    Создаём необходимые таблицы.
    """

    with get_db() as db:

        # -------------------------------------------------
        # УЧАСТНИКИ
        # -------------------------------------------------

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

        # -------------------------------------------------
        # КУПОНЫ
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

                status TEXT NOT NULL DEFAULT 'active',

                FOREIGN KEY (user_id)
                    REFERENCES users(user_id)
            )
            """
        )

        # -------------------------------------------------
        # СЧЁТЧИК КУПОНОВ
        # -------------------------------------------------

        db.execute(
            """
            CREATE TABLE IF NOT EXISTS coupon_counter (
                id INTEGER PRIMARY KEY CHECK (id = 1),

                current_number INTEGER NOT NULL
            )
            """
        )

        # -------------------------------------------------
        # Индексы
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

        db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_coupons_status
            ON coupons(status)
            """
        )

        # -------------------------------------------------
        # Инициализируем счётчик
        # -------------------------------------------------

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
                (INITIAL_COUPON_NUMBER,)
            )

            logging.info(
                f"Счётчик купонов установлен на "
                f"{INITIAL_COUPON_NUMBER}"
            )

        db.commit()

    logging.info(
        f"База данных инициализирована: {DB_NAME}"
    )


# =========================================================
# USERS
# =========================================================

def get_user(user_id: int):
    """
    Получаем участника.
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
    phone: str
):
    """
    Создаём участника.
    """

    created_at = datetime.now(
        timezone.utc
    ).isoformat()

    with get_db() as db:

        db.execute(
            """
            INSERT INTO users (
                user_id,
                phone,
                coupon,
                created_at
            )
            VALUES (?, ?, NULL, ?)
            """,
            (
                user_id,
                phone,
                created_at
            )
        )

        db.commit()

    logging.info(
        f"Пользователь сохранён: "
        f"user_id={user_id}, phone={phone}"
    )


# =========================================================
# COUPON NUMBER
# =========================================================

def get_next_coupon_number():
    """
    Получаем следующий номер купона.

    01268
    01269
    01270
    ...
    """

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

            current_number = INITIAL_COUPON_NUMBER

            db.execute(
                """
                INSERT INTO coupon_counter (
                    id,
                    current_number
                )
                VALUES (1, ?)
                """,
                (current_number,)
            )

        else:

            current_number = row["current_number"]

        next_number = current_number + 1

        db.execute(
            """
            UPDATE coupon_counter
            SET current_number = ?
            WHERE id = 1
            """,
            (next_number,)
        )

        db.commit()

    logging.info(
        f"Выдан следующий номер купона: "
        f"{current_number:05d}"
    )

    return current_number


# =========================================================
# COUPON EXPIRATION
# =========================================================

def add_one_month(dt):
    """
    Добавляет ровно один календарный месяц.

    Например:

    19.08 → 19.09
    31.01 → 28.02
    """

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

def create_coupon(user_id: int):
    """
    Создаём новый купон для пользователя.

    Каждый вызов этой функции создаёт
    НОВЫЙ отдельный купон.

    Один пользователь может иметь
    несколько купонов.
    """

    created_at = datetime.now(
        timezone.utc
    )

    expires_at = add_one_month(
        created_at
    )

    # Получаем последовательный номер
    coupon_number = get_next_coupon_number()

    # Случайно выбираем приз
    prize = secrets.choice(PRIZES)

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
        "СОЗДАН КУПОН: "
        f"номер={coupon_number:05d}, "
        f"user_id={user_id}, "
        f"prize={prize}, "
        f"expires={expires_at.isoformat()}"
    )

    return (
        coupon_number,
        prize,
        created_at,
        expires_at
    )


# =========================================================
# COUPON STATISTICS
# =========================================================

def get_coupons_count():
    """
    Всего выдано купонов.
    """

    with get_db() as db:

        cursor = db.execute(
            """
            SELECT COUNT(*)
            FROM coupons
            """
        )

        return cursor.fetchone()[0]


def get_active_coupons_count():
    """
    Количество активных купонов.
    """

    with get_db() as db:

        cursor = db.execute(
            """
            SELECT COUNT(*)
            FROM coupons
            WHERE status = 'active'
            """
        )

        return cursor.fetchone()[0]


def get_last_coupon():
    """
    Последний выданный купон.
    """

    with get_db() as db:

        cursor = db.execute(
            """
            SELECT *
            FROM coupons
            ORDER BY coupon_number DESC
            LIMIT 1
            """
        )

        return cursor.fetchone()


# =========================================================
# PHONE
# =========================================================

def normalize_phone(phone: str) -> str:
    """
    Приводим российский номер к формату 7XXXXXXXXXX.
    """

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
    """
    Проверяем российский номер.
    """

    digits = normalize_phone(phone)

    return (
        len(digits) == 11
        and digits.startswith("7")
    )


# =========================================================
# CONTACT
# =========================================================

def get_phone_from_event(event):
    """
    Получаем телефон из контакта MAX.
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

            # payload.phone
            phone = getattr(
                payload,
                "phone",
                None
            )

            if phone:
                return phone

            # VCF
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
# PROCESS PHONE
# =========================================================

async def process_phone(
    event,
    user_id: int,
    phone: str
):
    """
    Обрабатываем телефон и выдаём купон.
    """

    # Проверяем номер
    if not is_phone(phone):

        await event.message.answer(
            "❌ Не удалось распознать номер телефона.\n\n"
            "Попробуйте поделиться номером ещё раз."
        )

        return

    phone = normalize_phone(phone)

    # -----------------------------------------------------
    # Проверяем пользователя
    # -----------------------------------------------------

    existing_user = get_user(user_id)

    if existing_user:

        logging.info(
            f"Пользователь уже есть в БД: "
            f"user_id={user_id}"
        )

        # ВАЖНО:
        # Теперь мы НЕ выдаём старый купон.
        #
        # Каждый успешный запрос телефона
        # создаёт новый отдельный купон.
        #
        # Поэтому пользователь может получить:
        #
        # 01268
        # 01269
        # 01270
        #
        # и т.д.

    else:

        # Новый пользователь
        try:

            create_user(
                user_id=user_id,
                phone=phone
            )

        except sqlite3.IntegrityError:

            await event.message.answer(
                "❌ Этот номер телефона уже "
                "использовался для получения купона."
            )

            waiting_phone.discard(user_id)

            return

    # -----------------------------------------------------
    # Создаём новый купон
    # -----------------------------------------------------

    try:

        (
            coupon_number,
            prize,
            created_at,
            expires_at
        ) = create_coupon(user_id)

    except Exception as e:

        logging.exception(
            f"Ошибка создания купона: {e}"
        )

        await event.message.answer(
            "❌ Произошла ошибка при создании купона.\n\n"
            "Попробуйте ещё раз."
        )

        return

    waiting_phone.discard(user_id)

    # -----------------------------------------------------
    # Форматируем дату
    # -----------------------------------------------------

    created_text = created_at.strftime(
        "%d.%m.%Y"
    )

    expires_text = expires_at.strftime(
        "%d.%m.%Y"
    )

    # -----------------------------------------------------
    # Отправляем купон
    # -----------------------------------------------------

    await event.message.answer(
        "🎉 Поздравляем! Вы получили новый купон! 🎁\n\n"

        f"🎟 Номер купона: "
        f"{coupon_number:05d}\n\n"

        f"🎁 Ваш приз:\n"
        f"{prize}\n\n"

        f"📅 Выдан: {created_text}\n"
        f"⏳ Действует до: {expires_text}\n\n"

        "Покажите это сообщение администратору "
        "или сделайте скриншот."
    )

    logging.info(
        f"КУПОН ВЫДАН: "
        f"{coupon_number:05d} | "
        f"user_id={user_id} | "
        f"{prize}"
    )


# =========================================================
# ADMIN /USERS
# =========================================================

async def admin_users(event):

    user_id = event.message.sender.user_id

    if user_id not in ADMIN_IDS:

        await event.message.answer(
            "❌ У вас нет доступа к этой команде."
        )

        return

    users_count = get_users_count()

    coupons_count = get_coupons_count()

    active_count = get_active_coupons_count()

    last_coupon = get_last_coupon()

    text = (
        "👑 СТАТИСТИКА\n\n"

        f"👥 Участников: {users_count}\n"
        f"🎟 Всего купонов: {coupons_count}\n"
        f"🟢 Активных купонов: {active_count}\n"
    )

    if last_coupon:

        text += (
            "\n━━━━━━━━━━━━━━━━━━\n\n"

            "🎟 ПОСЛЕДНИЙ КУПОН\n\n"

            f"Номер: "
            f"{last_coupon['coupon_number']:05d}\n\n"

            f"Приз:\n"
            f"{last_coupon['prize']}\n\n"

            f"MAX user_id: "
            f"{last_coupon['user_id']}\n"
        )

    await event.message.answer(
        text
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

        await admin_users(event)

        return

    # =====================================================
    # CONTACT
    # =====================================================

    phone = get_phone_from_event(event)

    if phone:

        logging.info(
            f"Получен номер через кнопку: "
            f"user_id={user_id}, "
            f"phone={phone}"
        )

        await process_phone(
            event,
            user_id,
            phone
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
        attachments=[buttons]
    )


# =========================================================
# MAIN
# =========================================================

async def main():

    # Создаём / проверяем БД
    init_db()

    # Статистика при запуске
    users_count = get_users_count()

    coupons_count = get_coupons_count()

    logging.info(
        f"При запуске: "
        f"участников={users_count}, "
        f"купонов={coupons_count}"
    )

    logging.info(
        "Бот запускается..."
    )

    await dp.start_polling(bot)


# =========================================================
# START
# =========================================================

if __name__ == "__main__":

    asyncio.run(main())
