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
# ТОКЕН
# =========================================================

TOKEN = "ВСТАВЬ_СЮДА_НОВЫЙ_ТОКЕН"


# =========================================================
# АДМИНИСТРАТОРЫ
# =========================================================

ADMIN_IDS = {
    277114915
}


# =========================================================
# БАЗА ДАННЫХ
# =========================================================

DB_NAME = "users.db"


# =========================================================
# НОМЕР ПОСЛЕДНЕГО СТАРОГО КУПОНА
# =========================================================

# До запуска этого бота уже существовало:
#
# 01267
#
# Поэтому первый новый купон:
#
# 01268

INITIAL_COUPON_NUMBER = 1267


# =========================================================
# ПРИЗЫ
# =========================================================

# Всего 15 уникальных призов.
#
# Каждый приз имеет одинаковую вероятность:
#
# 1 / 15 = 6.67%

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

# Пользователи, от которых ждём телефон.

waiting_phone = set()


# =========================================================
# DATABASE
# =========================================================

def get_db():
    """
    Открываем соединение с SQLite.
    """

    connection = sqlite3.connect(DB_NAME)

    connection.row_factory = sqlite3.Row

    return connection


def init_db():
    """
    Создаём таблицы базы данных.

    Важно:
    существующая users.db не удаляется.
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

        db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_coupons_status
            ON coupons(status)
            """
        )

        # =================================================
        # ПРОВЕРЯЕМ СЧЁТЧИК
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
            (
                user_id,
            )
        )

        return cursor.fetchone()


def get_user_by_phone(phone: str):
    """
    Получаем пользователя по номеру телефона.
    """

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
    Создаём нового пользователя.

    Поле coupon оставляем для совместимости
    со старой версией базы.

    Все реальные новые купоны находятся
    в таблице coupons.
    """

    created_at = datetime.now(
        timezone.utc
    ).isoformat()

    # В старой версии таблицы coupon мог быть
    # NOT NULL и UNIQUE.
    #
    # Поэтому записываем туда уникальный технический
    # идентификатор профиля.
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

    logging.info(
        "Новый пользователь сохранён: "
        f"user_id={user_id}, "
        f"phone={phone}"
    )


# =========================================================
# COUPONS
# =========================================================

def get_coupons_count() -> int:
    """
    Общее количество выданных купонов.
    """

    with get_db() as db:

        cursor = db.execute(
            """
            SELECT COUNT(*)
            FROM coupons
            """
        )

        return cursor.fetchone()[0]


def get_active_coupons_count() -> int:
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


def get_user_coupons_count(
    user_id: int
) -> int:
    """
    Сколько купонов у конкретного пользователя.
    """

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
# СЛЕДУЮЩИЙ НОМЕР КУПОНА
# =========================================================

def get_next_coupon_number():
    """
    Получаем следующий номер купона.

    Первый:
        01268

    Потом:
        01269
        01270
        01271
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

        # Сразу увеличиваем счётчик.
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

    logging.info(
        "Следующий номер купона: "
        f"{current_number:05d}"
    )

    return current_number


# =========================================================
# + 1 МЕСЯЦ
# =========================================================

def add_one_month(dt):
    """
    Добавляем один календарный месяц.

    19.08 → 19.09

    Если дата попадает в конец месяца,
    корректируем последний день.
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
# СОЗДАНИЕ КУПОНА
# =========================================================

def create_coupon(
    user_id: int
):
    """
    Создаём новый отдельный купон.

    Каждый вызов создаёт новый номер.

    Один пользователь может иметь:
        01268
        01269
        01270
        ...

    Каждый купон независимый.
    """

    created_at = datetime.now(
        timezone.utc
    )

    expires_at = add_one_month(
        created_at
    )

    # Получаем следующий номер.
    coupon_number = (
        get_next_coupon_number()
    )

    # Равновероятный случайный приз.
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
        "НОВЫЙ КУПОН: "
        f"{coupon_number:05d} | "
        f"user_id={user_id} | "
        f"prize={prize}"
    )

    return (
        coupon_number,
        prize,
        created_at,
        expires_at
    )


# =========================================================
# PHONE
# =========================================================

def normalize_phone(
    phone: str
) -> str:
    """
    Приводим российский номер
    к формату 7XXXXXXXXXX.
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
        digits = (
            "7" + digits[1:]
        )

    return digits


def is_phone(
    phone: str
) -> bool:
    """
    Проверяем российский номер.
    """

    digits = normalize_phone(
        phone
    )

    return (
        len(digits) == 11
        and digits.startswith("7")
    )


# =========================================================
# ПОЛУЧЕНИЕ ТЕЛЕФОНА ИЗ КОНТАКТА MAX
# =========================================================

def get_phone_from_event(event):
    """
    Пытаемся получить номер телефона
    из контактного вложения MAX.
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

            # -------------------------------------------------
            # Вариант 1: payload.phone
            # -------------------------------------------------

            phone = getattr(
                payload,
                "phone",
                None
            )

            if phone:
                return phone

            # -------------------------------------------------
            # Вариант 2: VCF
            # -------------------------------------------------

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
                        match.group(1)
                        .strip()
                    )

    except Exception as e:

        logging.exception(
            "Ошибка при получении "
            f"номера из контакта: {e}"
        )

    return None


# =========================================================
# ОТПРАВКА КУПОНА ПОЛЬЗОВАТЕЛЮ
# =========================================================

async def send_coupon(
    event,
    user_id: int
):
    """
    Создаёт и отправляет новый купон.
    """

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

    user_coupons = (
        get_user_coupons_count(
            user_id
        )
    )

    await event.message.answer(

        "🎉 Поздравляем! "
        "Вы получили новый купон! 🎁\n\n"

        f"🎟 НОМЕР КУПОНА:\n"
        f"{coupon_number:05d}\n\n"

        f"🎁 ВАШ ПРИЗ:\n"
        f"{prize}\n\n"

        f"📅 Выдан: {created_text}\n"
        f"⏳ Действует до: {expires_text}\n\n"

        f"🎟 Всего ваших купонов: "
        f"{user_coupons}\n\n"

        "Покажите это сообщение "
        "администратору или сделайте скриншот."
    )


# =========================================================
# ОБРАБОТКА ТЕЛЕФОНА
# =========================================================

async def process_phone(
    event,
    user_id: int,
    phone: str
):
    """
    Обработка телефона.

    ВАЖНО:

    Первый раз:
        регистрация + первый купон.

    Повторная отправка телефона:
        НОВЫЙ купон НЕ выдаём.

    Новый купон можно получить
    через команду /coupon.
    """

    # =====================================================
    # Проверяем телефон
    # =====================================================

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

    # =====================================================
    # Проверяем пользователя по MAX user_id
    # =====================================================

    existing_user = get_user(
        user_id
    )

    if existing_user:

        waiting_phone.discard(
            user_id
        )

        logging.info(
            "Повторная отправка телефона. "
            f"user_id={user_id}. "
            "Новый купон НЕ выдаём."
        )

        coupons_count = (
            get_user_coupons_count(
                user_id
            )
        )

        await event.message.answer(
            "ℹ️ Вы уже зарегистрированы.\n\n"

            "Ваш номер телефона уже "
            "сохранён в базе.\n\n"

            f"🎟 У вас купонов: "
            f"{coupons_count}\n\n"

            "Повторная отправка номера "
            "не создаёт новый купон.\n\n"

            "Если вам нужно получить "
            "ещё один купон, используйте:\n"
            "/coupon"
        )

        return

    # =====================================================
    # Проверяем телефон
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
            "зарегистрирован в системе."
        )

        logging.warning(
            "Попытка зарегистрировать "
            f"уже существующий телефон: {phone}"
        )

        return

    # =====================================================
    # Создаём пользователя
    # =====================================================

    try:

        create_user(
            user_id=user_id,
            phone=phone
        )

    except sqlite3.IntegrityError:

        waiting_phone.discard(
            user_id
        )

        logging.exception(
            "Ошибка регистрации пользователя."
        )

        await event.message.answer(
            "❌ Не удалось сохранить "
            "данные пользователя.\n\n"
            "Попробуйте ещё раз."
        )

        return

    # =====================================================
    # Первый купон
    # =====================================================

    waiting_phone.discard(
        user_id
    )

    await send_coupon(
        event,
        user_id
    )


# =========================================================
# ADMIN /USERS
# =========================================================

async def admin_users(
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

    coupons_count = (
        get_coupons_count()
    )

    active_count = (
        get_active_coupons_count()
    )

    last_coupon = (
        get_last_coupon()
    )

    text = (

        "👑 СТАТИСТИКА БОТА\n\n"

        f"👥 Участников: "
        f"{users_count}\n"

        f"🎟 Всего купонов: "
        f"{coupons_count}\n"

        f"🟢 Активных купонов: "
        f"{active_count}\n"
    )

    if last_coupon:

        text += (

            "\n━━━━━━━━━━━━━━━━━━\n\n"

            "🎟 ПОСЛЕДНИЙ КУПОН\n\n"

            f"Номер: "
            f"{last_coupon['coupon_number']:05d}\n\n"

            f"Приз:\n"
            f"{last_coupon['prize']}\n\n"

            f"MAX user_id:\n"
            f"{last_coupon['user_id']}\n"
        )

    await event.message.answer(
        text
    )


# =========================================================
# /COUPON
# =========================================================

async def user_coupon(
    event
):
    """
    Выдача дополнительного купона.

    Повторная отправка телефона новый купон
    не выдаёт.

    А команда /coupon выдаёт новый отдельный
    купон с новым номером.
    """

    user_id = (
        event.message.sender.user_id
    )

    user = get_user(
        user_id
    )

    # -----------------------------------------------------
    # Пользователь ещё не зарегистрирован
    # -----------------------------------------------------

    if user is None:

        await event.message.answer(
            "❗ Сначала нужно зарегистрироваться.\n\n"

            "Нажмите кнопку "
            "«📱 Поделиться номером» "
            "и отправьте свой номер телефона."
        )

        waiting_phone.add(
            user_id
        )

        return

    # -----------------------------------------------------
    # Пользователь зарегистрирован
    # -----------------------------------------------------

    logging.info(
        f"Пользователь запросил "
        f"новый купон: user_id={user_id}"
    )

    await send_coupon(
        event,
        user_id
    )


# =========================================================
# ОБРАБОТЧИК СООБЩЕНИЙ
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

    # =====================================================
    # ТЕКСТ
    # =====================================================

    text = (
        getattr(
            event.message.body,
            "text",
            None
        )
        or ""
    ).strip()

    text_lower = text.lower()

    # =====================================================
    # /users
    # =====================================================

    if text_lower == "/users":

        await admin_users(
            event
        )

        return

    # =====================================================
    # /coupon
    # =====================================================

    if text_lower == "/coupon":

        await user_coupon(
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
            "Получен контакт: "
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

    # =====================================================
    # КНОПКА ПОДЕЛИТЬСЯ НОМЕРОМ
    # =====================================================

    buttons = (
        ButtonsPayload(
            buttons=[
                [
                    RequestContactButton(
                        text="📱 Поделиться номером"
                    )
                ]
            ]
        ).pack()
    )

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

            "Чтобы он стал вашим, бот должен "
            "убедиться, что вы — реальный человек.\n\n"

            "Для подтверждения нажмите кнопку "
            "ниже и поделитесь своим номером "
            "телефона.\n\n"

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

    # -----------------------------------------------------
    # Инициализируем БД
    # -----------------------------------------------------

    init_db()

    # -----------------------------------------------------
    # Статистика при запуске
    # -----------------------------------------------------

    users_count = (
        get_users_count()
    )

    coupons_count = (
        get_coupons_count()
    )

    logging.info(
        "При запуске: "
        f"участников={users_count}, "
        f"купонов={coupons_count}"
    )

    logging.info(
        "Бот запускается..."
    )

    # -----------------------------------------------------
    # Запуск MAX
    # -----------------------------------------------------

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
