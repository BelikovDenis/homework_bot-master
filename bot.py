import os
import threading
import telebot  # type: ignore
from telebot import types  # type: ignore

from database import (
    init_db,
    DB,
    add_reminder,
    get_reminders,
    delete_reminder,
    get_shopping_list,
    add_shopping_item,
    delete_shopping_item,
)

from dotenv import load_dotenv  # type: ignore
from datetime import datetime, timedelta
from utils import schedule_checker


load_dotenv()
bot = telebot.TeleBot(os.getenv("TELEGRAM_TOKEN"))
init_db()


USER_STATES = {}


def get_main_markup():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    buttons = ["📝 Напоминания", "🛒 Список покупок", "💡 Предложить функционал"]
    markup.add(*buttons)
    return markup


@bot.message_handler(commands=["start"])
def start(message):
    user_id = message.from_user.id
    with DB() as cursor:
        cursor.execute(
            "INSERT OR IGNORE INTO users (user_id, created) VALUES (?, ?)",
            (user_id, datetime.now()),
        )
    bot.send_message(
        message.chat.id,
        "Привет! Я твой ежедневный помощник. Выбери действие:",
        reply_markup=get_main_markup(),
    )


@bot.message_handler(func=lambda m: m.text == "📝 Напоминания")
def handle_reminders(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("Создать", callback_data="create_reminder"),
        types.InlineKeyboardButton("Мои напоминания", callback_data="list_reminders"),
        types.InlineKeyboardButton("Удалить", callback_data="delete_reminder"),
    )
    bot.send_message(message.chat.id, "Управление напоминаниями:", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data == "create_reminder")
def create_reminder(call):
    USER_STATES[call.from_user.id] = {"step": "reminder_text"}
    bot.send_message(call.message.chat.id, "Введите текст напоминания:")


@bot.message_handler(
    func=lambda m: USER_STATES.get(m.from_user.id, {}).get("step") == "reminder_text"
)
def process_reminder_text(message):
    user_id = message.from_user.id
    USER_STATES[user_id] = {"step": "reminder_date", "text": message.text}
    bot.send_message(
        message.chat.id,
        "Введите дату и время в формате ЧЧ:ММ ДД.ММ.ГГГГ (например, 14:30 31.12.2023):",
    )


@bot.message_handler(
    func=lambda m: USER_STATES.get(m.from_user.id, {}).get("step") == "reminder_date"
)
def process_reminder_date(message):
    """Обработка даты с поддержкой 'сегодня' и 'завтра'"""
    user_id = message.from_user.id
    try:
        # Парсим ввод пользователя
        if " " in message.text:  # Если есть пробел - время и дата
            time_str, date_str = message.text.split()
        else:  # Только время - подставляем сегодня/завтра
            time_str = message.text
            now = datetime.now()
            if now.hour > int(time_str.split(":")[0]) or (
                now.hour == int(time_str.split(":")[0])
                and now.minute >= int(time_str.split(":")[1])
            ):
                date_str = "завтра"
            else:
                date_str = "сегодня"

        # Обработка специальных значений даты
        if date_str.lower() == "сегодня":
            dt_date = datetime.now().date()
        elif date_str.lower() == "завтра":
            dt_date = (datetime.now() + timedelta(days=1)).date()
        else:
            day, month, year = map(int, date_str.split("."))
            dt_date = datetime(year, month, day).date()

        # Парсим время
        hours, minutes = map(int, time_str.split(":"))
        dt = datetime.combine(dt_date, datetime.min.time()).replace(
            hour=hours, minute=minutes
        )

        # Проверка на прошедшее время
        if dt < datetime.now() - timedelta(minutes=1):
            bot.send_message(
                message.chat.id,
                "Дата в прошлом! Используйте 'завтра' для вечерних напоминаний",
            )
            return

        USER_STATES[user_id] = {
            "step": "reminder_repeat",
            "text": USER_STATES[user_id]["text"],
            "date": dt,
        }

        # Клавиатура для выбора периодичности
        markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add("Ежедневно", "Еженедельно", "Ежемесячно", "Ежегодно", "Один раз")
        bot.send_message(
            message.chat.id, "Выберите периодичность:", reply_markup=markup
        )

    except Exception as e:
        bot.send_message(
            message.chat.id, "Ошибка формата! Примеры:\n14:30 завтра\n18:00 31.12.2023"
        )
        print(f"Date processing error: {e}")


@bot.message_handler(
    func=lambda m: USER_STATES.get(m.from_user.id, {}).get("step") == "reminder_repeat"
)
def process_reminder_repeat(message):
    user_id = message.from_user.id
    repeat_map = {
        "Ежедневно": "daily",
        "Еженедельно": "weekly",
        "Ежемесячно": "monthly",
        "Ежегодно": "yearly",
        "Один раз": None,
    }
    repeat = repeat_map.get(message.text)

    dt = USER_STATES[user_id]["date"]

    add_reminder(user_id, USER_STATES[user_id]["text"], dt, repeat=repeat)
    local_time = dt.strftime("%H:%M %d.%m.%Y")
    bot.send_message(
        message.chat.id,
        f"✅ Напоминание создано на {local_time}",
        reply_markup=get_main_markup(),
    )
    del USER_STATES[user_id]


@bot.callback_query_handler(func=lambda call: call.data == "list_reminders")
def list_reminders(call):
    reminders = get_reminders(call.from_user.id)
    if not reminders:
        bot.send_message(call.message.chat.id, "У вас нет активных напоминаний.")
        return

    text = "Ваши напоминания:\n\n"
    for rem in reminders:
        text += f"{rem[0]}. {rem[1]} - {rem[2].strftime('%H:%M %d.%m.%Y')}"
        if rem[3]:
            text += f" (повтор: {rem[3]})"
        text += "\n"

    bot.send_message(call.message.chat.id, text)


@bot.callback_query_handler(func=lambda call: call.data == "delete_reminder")
def delete_reminder_callback(call):
    USER_STATES[call.from_user.id] = {"step": "delete_reminder"}
    bot.send_message(call.message.chat.id, "Введите ID напоминания для удаления:")


@bot.message_handler(
    func=lambda m: USER_STATES.get(m.from_user.id, {}).get("step") == "delete_reminder"
)
def process_delete_reminder(message):
    user_id = message.from_user.id
    try:
        rem_id = int(message.text)
        delete_reminder(rem_id)
        bot.send_message(
            message.chat.id, "Напоминание удалено!", reply_markup=get_main_markup()
        )
    except ValueError:
        bot.send_message(message.chat.id, "Неверный ID. Введите число.")
    finally:
        if user_id in USER_STATES:
            del USER_STATES[user_id]


# В функции handle_shopping_list добавляем новую кнопку
@bot.message_handler(func=lambda m: m.text == "🛒 Список покупок")
def handle_shopping_list(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("Добавить", callback_data="add_item"),
        types.InlineKeyboardButton("Список", callback_data="show_list"),
        types.InlineKeyboardButton(
            "Удалить всё", callback_data="delete_all_items"
        ),  # Новая кнопка
        types.InlineKeyboardButton("Удалить", callback_data="delete_item"),
    )
    bot.send_message(
        message.chat.id, "Управление списком покупок:", reply_markup=markup
    )


@bot.callback_query_handler(func=lambda call: call.data == "add_item")
def add_shopping_item_callback(call):
    USER_STATES[call.from_user.id] = {"action": "add_item", "step": "item"}
    bot.send_message(call.message.chat.id, "Введите название товара:")


# Добавляем кнопку для полной очистки списка покупок
@bot.callback_query_handler(func=lambda call: call.data == "delete_all_items")
def delete_all_shopping_items(call):
    with DB() as cursor:
        cursor.execute(
            "DELETE FROM shopping_list WHERE user_id = ?", (call.from_user.id,)
        )
    bot.answer_callback_query(call.id, "Весь список удален!")
    bot.send_message(
        call.message.chat.id, "Список покупок очищен.", reply_markup=get_main_markup()
    )


@bot.message_handler(
    func=lambda m: USER_STATES.get(m.from_user.id, {}).get("step") == "item"
)
def process_shopping_item(message):
    user_id = message.from_user.id
    USER_STATES[user_id] = {
        "action": "add_item",
        "step": "category",
        "item": message.text,
    }
    bot.send_message(
        message.chat.id, "Введите категорию товара (если не требуется, отправьте '-'):"
    )


@bot.message_handler(
    func=lambda m: USER_STATES.get(m.from_user.id, {}).get("step") == "category"
)
def process_shopping_category(message):
    user_id = message.from_user.id
    category = message.text.strip()
    if category == "-":
        category = "Без категории"
    add_shopping_item(user_id, USER_STATES[user_id]["item"], category)
    bot.send_message(
        message.chat.id,
        "Товар добавлен в список покупок!",
        reply_markup=get_main_markup(),
    )
    del USER_STATES[user_id]


@bot.callback_query_handler(func=lambda call: call.data == "show_list")
def show_shopping_list(call):
    items = get_shopping_list(call.from_user.id)
    if not items:
        bot.send_message(call.message.chat.id, "Ваш список покупок пуст.")
        return

    items_by_category = {}
    for item in items:
        category = item[2] if item[2] else "Без категории"
        if category not in items_by_category:
            items_by_category[category] = []
        items_by_category[category].append(item[1])

    text = "Ваш список покупок:\n\n"
    for category in items_by_category:
        text += f"<b>{category}:</b>\n"
        text += "\n".join(f"• {item}" for item in items_by_category[category])
        text += "\n\n"

    bot.send_message(call.message.chat.id, text, parse_mode="HTML")


@bot.callback_query_handler(func=lambda call: call.data == "delete_item")
def delete_shopping_item_callback(call):
    items = get_shopping_list(call.from_user.id)
    if not items:
        bot.send_message(call.message.chat.id, "Ваш список покупок пуст.")
        return

    markup = types.InlineKeyboardMarkup()
    for item in items:
        markup.add(
            types.InlineKeyboardButton(
                f"{item[1]} ({item[2]})", callback_data=f"delete_item_{item[0]}"
            )
        )

    bot.send_message(
        call.message.chat.id, "Выберите товар для удаления:", reply_markup=markup
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_item_"))
def process_delete_item(call):
    item_id = call.data.split("_")[-1]
    delete_shopping_item(item_id)
    bot.answer_callback_query(call.id, "Товар удален!")
    bot.delete_message(call.message.chat.id, call.message.message_id)
    bot.send_message(
        call.message.chat.id, "Товар успешно удален.", reply_markup=get_main_markup()
    )


@bot.message_handler(func=lambda m: m.text == "💡 Предложить функционал")
def suggest_feature(message):
    bot.send_message(
        message.chat.id, "Ваши предложения по улучшению бота отправляйте разработчику."
    )


@bot.message_handler(commands=["export"])
def export_data(message):
    user_id = message.from_user.id
    reminders = get_reminders(user_id)
    if reminders:
        reminders_csv = "ID,Текст,Дата,Повтор\n"
        for rem in reminders:
            reminders_csv += f"{rem[0]},{rem[1]},{rem[2].strftime('%d.%m.%Y %H:%M')},{rem[3] or 'нет'}\n"
        bot.send_document(message.chat.id, ("reminders.csv", reminders_csv))
    else:
        bot.send_message(message.chat.id, "У вас нет напоминаний для экспорта.")

    items = get_shopping_list(user_id)
    if items:
        items_csv = "ID,Товар,Категория\n"
        for item in items:
            items_csv += f"{item[0]},{item[1]},{item[2]}\n"
        bot.send_document(message.chat.id, ("shopping_list.csv", items_csv))
    else:
        bot.send_message(message.chat.id, "Ваш список покупок пуст.")


if __name__ == "__main__":
    threading.Thread(target=schedule_checker, args=(bot,), daemon=True).start()
    bot.infinity_polling()
