"""Модуль для сбора денег за игры."""

from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)


class PaymentStates(StatesGroup):
    """Состояния для сбора информации об оплате."""

    waiting_for_cost = State()
    waiting_for_phone = State()
    waiting_for_bank = State()
    waiting_for_custom_bank = State()


router = Router()

BANKS = [
    "Сбербанк", "Тинькофф", "Альфа-Банк", "Другой банк",
]


def create_yes_no_keyboard(game_date: str) -> InlineKeyboardMarkup:
    """Клавиатура да/нет для предложения сбора денег."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Да", callback_data=f"payment_yes_{game_date}"),
                InlineKeyboardButton(text="Нет", callback_data="delete_message"),
            ],
        ],
    )


def create_banks_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с банками."""
    keyboard = []
    for i in range(0, len(BANKS), 2):
        row = []
        for j in range(i, min(i + 2, len(BANKS))):
            bank = BANKS[j]
            callback_data = f"bank_{bank.lower().replace(' ', '_').replace('-', '_')}"
            row.append(InlineKeyboardButton(text=bank, callback_data=callback_data))
        keyboard.append(row)

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def create_phone_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура для отправки контакта."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Отправить номер", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def create_payment_done_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура подтверждения оплаты."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Сделано!", callback_data="payment_done")],
        ],
    )


async def send_payment_offer(bot: Bot, admin_id: int, game_date: str, game_time: str) -> None:
    """Отправить предложение о сборе денег админу."""
    text = (
        f"🎾 <b>Классно поиграли!</b>\n\n"
        f"Игра {game_date} в {game_time} завершена.\n"
        f"Нужна помощь в сборе денег за игру?"
    )

    await bot.send_message(
        admin_id,
        text,
        parse_mode="HTML",
        reply_markup=create_yes_no_keyboard(game_date),
    )


@router.callback_query(F.data.startswith("payment_yes_"))
async def accept_payment(callback: CallbackQuery, state: FSMContext) -> None:
    """Начало сбора информации об оплате."""
    game_date = callback.data.replace("payment_yes_", "")
    await state.update_data(game_date=game_date)

    await callback.message.edit_text(
        "💰 <b>Сбор денег за игру</b>\n\n"
        "Какая была стоимость корта в рублях?\n"
        "Введите только число:",
        parse_mode="HTML",
    )
    await state.set_state(PaymentStates.waiting_for_cost)
    await callback.answer()


@router.message(StateFilter(PaymentStates.waiting_for_cost))
async def handle_cost(message: Message, state: FSMContext) -> None:
    """Обработка ввода стоимости."""
    cost = int(message.text.strip())
    await state.update_data(cost=cost)

    await message.reply(
        "📱 <b>Номер для переводов</b>\n\n"
        "Отправьте номер телефона или используйте кнопку:",
        parse_mode="HTML",
        reply_markup=create_phone_keyboard(),
    )
    await state.set_state(PaymentStates.waiting_for_phone)


@router.message(StateFilter(PaymentStates.waiting_for_phone), F.contact)
async def handle_contact(message: Message, state: FSMContext) -> None:
    """Обработка контакта."""
    phone = message.contact.phone_number
    await state.update_data(phone=phone)
    await _ask_for_bank(message)


@router.message(StateFilter(PaymentStates.waiting_for_phone), F.text)
async def handle_phone_text(message: Message, state: FSMContext) -> None:
    """Обработка текстового ввода телефона."""
    phone = message.text.strip()
    await state.update_data(phone=phone)
    await _ask_for_bank(message)


async def _ask_for_bank(message: Message) -> None:
    """Запросить выбор банка."""
    await message.reply(
        "🏦 <b>Выберите банк</b>\n\n"
        "На какой банк переводить деньги?",
        parse_mode="HTML",
        reply_markup=create_banks_keyboard(),
    )


@router.callback_query(F.data.startswith("bank_"), StateFilter(PaymentStates.waiting_for_phone))
async def handle_bank_from_phone_state(callback: CallbackQuery, state: FSMContext, db) -> None:  # noqa: ANN001
    """Обработка выбора банка после ввода телефона."""
    await state.set_state(PaymentStates.waiting_for_bank)
    await handle_bank(callback, state, callback.bot, db)


@router.callback_query(F.data.startswith("bank_"), StateFilter(PaymentStates.waiting_for_bank))
async def handle_bank(callback: CallbackQuery, state: FSMContext, bot: Bot, db) -> None:  # noqa: ANN001
    """Обработка выбора банка."""
    bank_code = callback.data.replace("bank_", "")

    if bank_code == "другой_банк":
        await callback.message.edit_text(
            "🏦 <b>Название банка</b>\n\n"
            "Напишите название банка:",
            parse_mode="HTML",
        )
        await state.set_state(PaymentStates.waiting_for_custom_bank)
        return

    bank_name = bank_code.replace("_", " ").title()
    await _finish_payment_setup(callback, state, bot, bank_name, db)


async def _finish_payment_setup(  # noqa: PLR0913
        callback,  # noqa: ANN001
        state: FSMContext,
        bot: Bot,
        bank_name: str,
        db,  # noqa: ANN001
        *,
        custom: bool = False,
) -> None:
    """Завершение настройки и отправка запросов."""
    data = await state.get_data()
    cost = data["cost"]
    phone = data["phone"]
    game_date = data["game_date"]
    cost_per_person = cost // 4
    await state.clear()

    if phone.startswith("7"):
        phone = "+" + phone

    summary_text = (
        f"✅ <b>Данные собраны!</b>\n\n"
        f"💰 Стоимость корта: {cost} руб.\n"
        f"📱 Номер: {phone}\n"
        f"🏦 Банк: {bank_name}\n"
        f"💸 К доплате с человека: {cost_per_person} руб.\n\n"
        f"Отправил запросы другим игрокам!"
    )

    if custom:
        await callback.message.reply(summary_text, parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
    else:
        await callback.message.edit_text(summary_text, parse_mode="HTML")

    await _send_payment_requests(
        bot=bot,
        database=db,
        admin_id=callback.from_user.id,
        game_date=game_date,
        cost_per_person=cost_per_person,
        phone=phone,
        bank_name=bank_name,
    )

    await callback.answer("Запросы отправлены!")


async def _send_payment_requests(  # noqa: PLR0913
        bot: Bot,
        database,  # noqa: ANN001
        admin_id: int,
        game_date: str,
        cost_per_person: int,
        phone: str,
        bank_name: str,
) -> None:
    """Отправить запросы на оплату игрокам."""
    # Парсим дату и находим игру
    game_datetime = datetime.strptime(game_date, "%d.%m.%Y")  # noqa: DTZ007
    game = await database.get_game_by_date(game_datetime)

    players = game.get_players()
    players_to_notify = [pid for pid in players if pid != admin_id]

    message_text = (
        f"💰 <b>Просьба об оплате игры</b>\n\n"
        f"К оплате: <b>{cost_per_person} руб.</b>\n"
        f"📱 Номер: <code>{phone}</code>\n"
        f"🏦 Банк: {bank_name}\n\n"
    )

    for player_id in players_to_notify:
        await bot.send_message(
            player_id,
            message_text,
            parse_mode="HTML",
            reply_markup=create_payment_done_keyboard(),
        )


@router.callback_query(F.data == "payment_done")
async def payment_confirmed(callback: CallbackQuery) -> None:
    """Подтверждение оплаты игроком."""
    await callback.message.delete()
    await callback.answer("✅ Спасибо!")


@router.message(StateFilter(PaymentStates.waiting_for_custom_bank))
async def handle_custom_bank(message: Message, state: FSMContext, bot: Bot, db) -> None:  # noqa: ANN001
    """Обработка ввода названия банка."""
    bank_name = message.text.strip()

    class FakeCallback:
        def __init__(self, msg) -> None:  # noqa: ANN001
            self.message = msg
            self.from_user = msg.from_user

        async def answer(self, text="") -> None:  # noqa: ANN001
            pass

    await _finish_payment_setup(FakeCallback(message), state, bot, bank_name, db, custom=True)
