import asyncio
import logging
import re

from maxapi import Bot, Dispatcher
from maxapi.types import MessageCreated

logging.basicConfig(level=logging.INFO)

TOKEN = "f9LHodD0cOLJZ_QQj9kIYtnBMD3eCbHBwsf0UQWM34VCwzIwHu7wFVCjZ47aEkfWXziwgMn1oScOGgBlLoF5"

print("========== ПРОВЕРКА ТОКЕНА ==========")
print("TOKEN задан:", bool(TOKEN))
print("Длина токена:", len(TOKEN))
print("Начало:", TOKEN[:5])
print("Конец:", TOKEN[-5:])
print("=====================================")

bot = Bot(TOKEN)
dp = Dispatcher()

# Пользователи, от которых ждём номер телефона
waiting_phone = set()


def is_phone(phone: str) -> bool:
    """Проверяем российский номер телефона."""
    digits = re.sub(r"\D", "", phone)

    return (
        len(digits) == 11
        and digits.startswith(("7", "8"))
    )


def get_phone_from_event(event):
    """
    Пытаемся достать номер телефона из контактного вложения MAX.
    """
    try:
        attachments = event.message.body.attachments or []

        for attachment in attachments:
            # Контакт может находиться в payload
            payload = getattr(attachment, "payload", None)

            if payload is None:
                continue

            # Возможные варианты имени поля
            phone = getattr(payload, "phone", None)

            if phone:
                return phone

            # VCF-информация
            vcf_info = getattr(payload, "vcf_info", None)

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
            f"Ошибка при получении номера из контакта: {e}"
        )

    return None


@dp.message_created()
async def messages(event: MessageCreated):

    user = event.message.sender
    user_id = user.user_id

    # Получаем обычный текст сообщения
    text = (
        getattr(event.message.body, "text", None)
        or ""
    ).strip()

    # =========================================================
    # 1. Пытаемся получить номер через кнопку "Поделиться номером"
    # =========================================================

    phone = get_phone_from_event(event)

    if phone:
        logging.info(
            f"Получен номер через кнопку от пользователя "
            f"{user_id}: {phone}"
        )

        if user_id in waiting_phone:
            waiting_phone.remove(user_id)

        if is_phone(phone):
            await event.message.answer(
                "🎉 Поздравляем! Вы получили новый купон! 🎁\n\n"
                "Вы можете показать данное сообщение администратору "
                "или выслать его скриншотом."
            )
        else:
            await event.message.answer(
                "❌ Не удалось распознать номер телефона.\n\n"
                "Попробуйте поделиться номером ещё раз."
            )

        return

    # =========================================================
    # 2. Если ждём номер — разрешаем ввести его вручную
    # =========================================================

    if user_id in waiting_phone:

        if is_phone(text):

            waiting_phone.remove(user_id)

            await event.message.answer(
                "🎉 Поздравляем! Вы получили новый купон! 🎁\n\n"
                "Вы можете показать данное сообщение администратору "
                "или выслать его скриншотом."
            )

        else:

            await event.message.answer(
                "❌ Это не похоже на номер телефона.\n\n"
                "Нажмите кнопку «📱 Поделиться номером» "
                "или отправьте номер вручную.\n\n"
                "Например: 89991234567"
            )

        return

    # =========================================================
    # 3. Первое сообщение пользователя
    # =========================================================

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

    await event.message.answer(
        text=(
            f"{user.first_name}, здравствуйте! 👋\n\n"
            "Вы нашли секретный подарок! 🎁\n\n"
            "Чтобы он стал вашим, бот должен убедиться, "
            "что вы — реальный человек.\n\n"
            "Для подтверждения нажмите кнопку ниже "
            "и поделитесь своим номером телефона.\n\n"
            "Или можете отправить номер вручную."
        ),
        attachments=[buttons]
    )


async def main():
    # Старые webhook удалять больше не нужно.
    # У вас уже настроен polling.
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
