"""Файл с клавиатурами."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

delete_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Удалить уведомление", callback_data="delete_message")],
    ],
)
