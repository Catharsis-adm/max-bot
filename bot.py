import asyncio
import logging
import re

from maxapi import Bot, Dispatcher
from maxapi.types import (
    MessageCreated,
    RequestContactButton,
    ButtonsPayload,
)

logging.basicConfig(level=logging.INFO)

TOKEN = "ВАШ_ТОКЕН"

bot = Bot(TOKEN)
dp = Dispatcher()

# Пользователи, от которых ждём номер телефона
waiting_phone = set()


def is_phone(phone: str) -> bool:
    digits = re.sub(r"\D", "", phone)

    if len(digits) == 11 and digits.startswith(("7", "8")):
        return True

    return False


@dp.message_created()
async def messages(event: MessageCreated):
    text = (event.message.body.text or "").strip()
    user = event.message.sender

    # Если ждём номер
    if user.user_id in waiting_phone:

        if is_phone(text):

            waiting_phone.remove(user.user_id)

            await event.message.answer(
                "🎉 Поздравляем! Вы получили новый купон! 🎁\n\n"
                "Вы можете показать данное сообщение администратору "
                "или выслать его скриншотом."
            )

        else:

            await event.message.answer(
                "❌ Это не похоже на номер телефона.\n\n"
                "Нажмите кнопку «📱 Поделиться номером» "
                "или отправьте номер вручную."
            )

        return

    # Запоминаем пользователя
    waiting_phone.add(user.user_id)

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

    # Отправляем сообщение с кнопкой
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
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
