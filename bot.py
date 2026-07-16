import asyncio
import logging
import re

from maxapi import Bot, Dispatcher
from maxapi.types import MessageCreated

logging.basicConfig(level=logging.INFO)

TOKEN = "f9LHodD0cOLJZ_QQj9kIYtnBMD3eCbHBwsf0UQWM34VCwzIwHu7wFVCjZ47aEkfWXziwgMn1oScOGgBlLoF5"

bot = Bot(TOKEN)
dp = Dispatcher()

# Пользователи, от которых ждём номер телефона
waiting_phone = set()

def is_phone(phone: str) -> bool:
    # Убираем всё кроме цифр
    digits = re.sub(r"\D", "", phone)

    # 89999999999
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
                "Попробуйте ещё раз."
            )

        return

    # Первое сообщение пользователя
    waiting_phone.add(user.user_id)

    await event.message.answer(
        f"{user.first_name}, здравствуйте! 👋\n\n"
        "Вы нашли секретный подарок! 🎁\n\n"
        "Чтобы он стал вашим, бот должен убедиться, "
        "что вы — реальный человек.\n\n"
        "Для подтверждения отправьте ваш номер телефона.\n\n"
        "Например:\n"
        "89991234567"
    )

async def main():
    try:
        await bot.delete_subscriptions()
        logging.info("Старые webhook-подписки удалены")
    except Exception as e:
        logging.warning(f"Не удалось удалить старые подписки: {e}")

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
