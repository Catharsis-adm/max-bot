import asyncio
import logging
import re
import secrets
import sqlite3
from datetime import datetime, timezone

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

# ВСТАВЬ СЮДА НОВЫЙ ТОКЕН БОТА
TOKEN = "f9LHodD0cOLJZ_QQj9kIYtnBMD3eCbHBwsf0UQWM34VCwzIwHu7wFVCjZ47aEkfWXziwgMn1oScOGgBlLoF5"

# MAX user_id администратора
ADMIN_IDS = {277114915}

# Файл базы данных
DB_NAME = "users.db"


# =========================================================
# БОТ
# =========================================================

bot = Bot(TOKEN)
dp = Dispatcher()


# Пользователи, от которых ждём телефон.
# Это временное состояние.
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
    Создаём таблицу пользователей.
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
        f"База данных инициализирована: {DB_NAME}"
    )


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

        user = cursor.fetchone()

        if user:
            logging.info(
                f"Пользователь найден в БД: "
                f"user_id={user_id}, "
                f"coupon={user['coupon']}"
            )
        else:
            logging.info(
                f"Пользователь НЕ найден в БД: "
                f"user_id={user_id}"
            )

        return user


def get_users_count() -> int:
    """
    Получаем количество участников.
    """

    with get_db() as db:

        cursor = db.execute(
            """
            SELECT COUNT(*)
            FROM users
            """
        )

        count = cursor.fetchone()[0]

    logging.info(
        f"КОЛИЧЕСТВО ПОЛЬЗОВАТЕЛЕЙ В БД: {count}"
    )

    return count


def get_last_user():
    """
    Получаем последнего зарегистрированного пользователя.
    """

    with get_db() as db:

        cursor = db.execute(
            """
            SELECT *
            FROM users
            ORDER BY id DESC
            LIMIT 1
            """
        )

        return cursor.fetchone()


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

    logging.info(
        "ПОЛЬЗОВАТЕЛЬ СОХРАНЁН В БД: "
        f"user_id={user_id}, "
        f"phone={phone}, "
        f"coupon={coupon}"
    )


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

    Пример:

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

            logging.info(
                f"Сгенерирован новый купон: {code}"
            )

            return code


# =========================================================
# CONTACT
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

        logging.info(
            f"Получены attachments: {attachments}"
        )

        for attachment in attachments:

            payload = getattr(
                attachment,
                "payload",
                None
            )

            if payload is None:
                continue

            # ---------------------------------------------
            # Вариант 1: payload.phone
            # ---------------------------------------------

            phone = getattr(
                payload,
                "phone",
                None
            )

            if phone:

                logging.info(
                    f"Телефон найден через payload.phone: "
                    f"{phone}"
                )

                return phone

            # ---------------------------------------------
            # Вариант 2: VCF
            # ---------------------------------------------

            vcf_info = getattr(
                payload,
                "vcf_info",
                None
            )

            if vcf_info:

                logging.info(
                    f"Получен VCF: {vcf_info}"
                )

                match = re.search(
                    r"TEL[^:]*:([^\r\n]+)",
                    vcf_info,
                    re.IGNORECASE
                )

                if match:

                    phone = match.group(1).strip()

                    logging.info(
                        f"Телефон найден через VCF: "
                        f"{phone}"
                    )

                    return phone

    except Exception as e:

        logging.exception(
            f"Ошибка при получении номера "
            f"из контакта: {e}"
        )

    logging.warning(
        "Телефон в событии не найден."
    )

    return None


# =========================================================
# ОБРАБОТКА ТЕЛЕФОНА
# =========================================================

async def process_phone(
    event,
    user_id: int,
    phone: str
):
    """
    Обрабатываем полученный телефон.

    1. Проверяем номер.
    2. Проверяем пользователя.
    3. Генерируем купон.
    4. Сохраняем пользователя.
    5. Отправляем купон.
    """

    logging.info(
        f"Начинаем обработку телефона: "
        f"user_id={user_id}, phone={phone}"
    )

    # -----------------------------------------------------
    # Проверка телефона
    # -----------------------------------------------------

    if not is_phone(phone):

        logging.warning(
            f"Некорректный телефон: {phone}"
        )

        await event.message.answer(
            "❌ Не удалось распознать номер телефона.\n\n"
            "Попробуйте поделиться номером ещё раз."
        )

        return

    phone = normalize_phone(phone)

    logging.info(
        f"Нормализованный телефон: {phone}"
    )

    # -----------------------------------------------------
    # Проверяем пользователя
    # -----------------------------------------------------

    existing_user = get_user(user_id)

    if existing_user:

        logging.info(
            f"Пользователь уже зарегистрирован: "
            f"user_id={user_id}"
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

    # -----------------------------------------------------
    # Генерируем купон
    # -----------------------------------------------------

    coupon = generate_coupon()

    # -----------------------------------------------------
    # Сохраняем пользователя
    # -----------------------------------------------------

    try:

        create_user(
            user_id=user_id,
            phone=phone,
            coupon=coupon
        )

    except sqlite3.IntegrityError as e:

        logging.exception(
            f"Ошибка сохранения пользователя "
            f"user_id={user_id}: {e}"
        )

        await event.message.answer(
            "❌ Этот номер телефона уже "
            "использовался для получения купона."
        )

        waiting_phone.discard(user_id)

        return

    # -----------------------------------------------------
    # Пользователь успешно создан
    # -----------------------------------------------------

    waiting_phone.discard(user_id)

    # Проверяем, что он реально появился в БД
    saved_user = get_user(user_id)

    if saved_user:

        logging.info(
            f"ПРОВЕРКА БД УСПЕШНА: "
            f"user_id={user_id}, "
            f"coupon={saved_user['coupon']}"
        )

    else:

        logging.error(
            f"КРИТИЧЕСКАЯ ОШИБКА: "
            f"user_id={user_id} не найден "
            f"после сохранения!"
        )

    # -----------------------------------------------------
    # Отправляем купон
    # -----------------------------------------------------

    await event.message.answer(
        "🎉 Поздравляем! Вы получили новый купон! 🎁\n\n"
        f"Ваш купон:\n\n"
        f"🎟 {coupon}\n\n"
        "Покажите это сообщение администратору "
        "или выслите его скриншотом."
    )

    logging.info(
        f"КУПОН ВЫДАН: "
        f"user_id={user_id}, "
        f"coupon={coupon}"
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

    logging.info(
        f"Сообщение: "
        f"user_id={user_id}, "
        f"text={text!r}"
    )

    # =====================================================
    # ADMIN: /users
    # =====================================================

    if text.lower() == "/users":

        logging.info(
            f"Команда /users от user_id={user_id}"
        )

        # Проверяем администратора
        if user_id not in ADMIN_IDS:

            logging.warning(
                f"Пользователь {user_id} "
                f"попытался использовать /users"
            )

            await event.message.answer(
                "❌ У вас нет доступа к этой команде."
            )

            return

        # Количество
        count = get_users_count()

        # Последний участник
        last_user = get_last_user()

        if last_user:

            # Форматируем дату
            created_at = last_user["created_at"]

            try:

                dt = datetime.fromisoformat(
                    created_at
                )

                created_at = dt.strftime(
                    "%d.%m.%Y %H:%M"
                )

            except Exception:

                pass

            statistics_text = (
                "👥 СТАТИСТИКА БОТА\n\n"

                f"Всего участников: {count}\n\n"

                "━━━━━━━━━━━━━━━━━━\n\n"

                "👤 ПОСЛЕДНИЙ УЧАСТНИК\n\n"

                f"MAX user_id: "
                f"{last_user['user_id']}\n"

                f"📱 Телефон: "
                f"{last_user['phone']}\n"

                f"🎟 Купон: "
                f"{last_user['coupon']}\n"

                f"📅 Регистрация: "
                f"{created_at}"
            )

        else:

            statistics_text = (
                "👥 СТАТИСТИКА БОТА\n\n"
                "Всего участников: 0\n\n"
                "Пока никто не зарегистрирован."
            )

        logging.info(
            f"/users: участников в БД = {count}"
        )

        await event.message.answer(
            statistics_text
        )

        return

    # =====================================================
    # CONTACT
    # =====================================================

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

    # =====================================================
    # ЕСЛИ ЖДЁМ ТЕЛЕФОН
    # =====================================================

    if user_id in waiting_phone:

        if is_phone(text):

            logging.info(
                f"Пользователь {user_id} "
                f"отправил телефон вручную."
            )

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

    # Создаём кнопку запроса контакта
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

    # Инициализация базы
    init_db()

    logging.info(
        f"Используется база: {DB_NAME}"
    )

    # Сразу покажем количество пользователей
    # при запуске.
    count = get_users_count()

    logging.info(
        f"При запуске в базе находится "
        f"{count} участников."
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
