import os
from umaxbot import Bot, Dispatcher
from umaxbot.types import InlineKeyboardMarkup, InlineKeyboardButton, Message

# Берем токен из переменной окружения
BOT_TOKEN = os.getenv("BOT_TOKEN", "f9LHodD0cOIDaws8b1l8j69CR1npvge7CYVSvTvk45VWeVyGtFoYYV3xggF7_XMHnpL_nr_rGfB5g0lMwqB_")

bot = Bot(BOT_TOKEN)
dp = Dispatcher(bot)

@dp.message()
async def on_message(message: Message):
    # Создаем кнопку для запроса контакта
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Поделиться номером", request_contact=True)]
    ])
    await bot.send_message(
        chat_id=message.sender.id,
        text="Привет! Нажми на кнопку, чтобы поделиться номером и получить подарок!",
        reply_markup=keyboard
    )

# Запускаем бота (правильный способ)
bot.run(dp)
