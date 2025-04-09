import os
import threading
import telebot
from telebot import types
from database import (
    init_db, DB, add_reminder, get_reminders,
    delete_reminder, get_shopping_list, add_shopping_item,
    delete_shopping_item
)
from dotenv import load_dotenv
from datetime import datetime
from utils import schedule_checker


load_dotenv()
bot = telebot.TeleBot(os.getenv('TELEGRAM_TOKEN'))
init_db()

USER_STATES = {}


def get_main_markup():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    buttons = ['📝 Напоминания', '🛒 Список покупок', '💡 Предложить функционал']
    markup.add(*buttons)
    return markup


@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    with DB() as cursor:
        cursor.execute(
            'INSERT OR IGNORE INTO users (user_id, created) VALUES (?, ?)',
            (user_id, datetime.now())
        )
    bot.send_message(
        message.chat.id,
        "Привет! Я твой ежедневный помощник. Выбери действие:",
        reply_markup=get_main_markup())


@bot.message_handler(func=lambda m: m.text == '📝 Напоминания')
def handle_reminders(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton('Создать', callback_data='create_reminder'),
        types.InlineKeyboardButton('Мои напоминания', callback_data='list_reminders'),
        types.InlineKeyboardButton('Удалить', callback_data='delete_reminder')
    )
    bot.send_message(message.chat.id, "Управление напоминаниями:", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data == 'create_reminder')
def create_reminder(call):
    USER_STATES[call.from_user.id] = {'step': 'reminder_text'}
    bot.send_message(call.message.chat.id, "Введите текст напоминания:")


@bot.message_handler(func=lambda m: USER_STATES.get(m.from_user.id, {}).get('step') == 'reminder_text')
def process_reminder_text(message):
    user_id = message.from_user.id
    USER_STATES[user_id] = {
        'step': 'reminder_date',
        'text': message.text
    }
    bot.send_message(message.chat.id, "Введите дату и время в формате ЧЧ:ММ ДД.ММ.ГГГГ (например, 14:30 31.12.2023):")


@bot.message_handler(func=lambda m: USER_STATES.get(m.from_user.id, {}).get('step') == 'reminder_date')
def process_reminder_date(message):
    user_id = message.from_user.id
    try:
        time_str, date_str = message.text.split()
        hours, minutes = map(int, time_str.split(':'))
        day, month, year = map(int, date_str.split('.'))
        
        dt = datetime(year, month, day, hours, minutes)
        
        USER_STATES[user_id] = {
            'step': 'reminder_repeat',
            'text': USER_STATES[user_id]['text'],
            'date': dt
        }
        
        markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add('Ежедневно', 'Еженедельно', 'Ежемесячно', 'Ежегодно', 'Один раз')
        bot.send_message(message.chat.id, "Выберите периодичность:", reply_markup=markup)
    except Exception as e:
        bot.send_message(message.chat.id, "Неверный формат! Используйте ЧЧ:ММ ДД.ММ.ГГГГ")


@bot.message_handler(func=lambda m: USER_STATES.get(m.from_user.id, {}).get('step') == 'reminder_repeat')
def process_reminder_repeat(message):
    user_id = message.from_user.id
    repeat_map = {
        'Ежедневно': 'daily',
        'Еженедельно': 'weekly',
        'Ежемесячно': 'monthly',
        'Ежегодно': 'yearly',
        'Один раз': None
    }
    repeat = repeat_map.get(message.text)
    
    dt = USER_STATES[user_id]['date']
    
    add_reminder(
        user_id,
        USER_STATES[user_id]['text'],
        dt,
        repeat=repeat
    )
    local_time = dt.strftime('%H:%M %d.%m.%Y')
    bot.send_message(message.chat.id, f"✅ Напоминание создано на {local_time}", reply_markup=get_main_markup())
    del USER_STATES[user_id]


@bot.callback_query_handler(func=lambda call: call.data == 'list_reminders')
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


@bot.callback_query_handler(func=lambda call: call.data == 'delete_reminder')
def delete_reminder_callback(call):
    USER_STATES[call.from_user.id] = {'step': 'delete_reminder'}
    bot.send_message(call.message.chat.id, "Введите ID напоминания для удаления:")


@bot.message_handler(func=lambda m: USER_STATES.get(m.from_user.id, {}).get('step') == 'delete_reminder')
def process_delete_reminder(message):
    user_id = message.from_user.id
    try:
        rem_id = int(message.text)
        delete_reminder(rem_id)
        bot.send_message(message.chat.id, "Напоминание удалено!", reply_markup=get_main_markup())
    except ValueError:
        bot.send_message(message.chat.id, "Неверный ID. Введите число.")
    finally:
        if user_id in USER_STATES:
            del USER_STATES[user_id]


@bot.message_handler(func=lambda m: m.text == '🛒 Список покупок')
def handle_shopping_list(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton('Добавить', callback_data='add_item'),
        types.InlineKeyboardButton('Список', callback_data='show_list'),
        types.InlineKeyboardButton('Удалить', callback_data='delete_item')
    )
    bot.send_message(message.chat.id, "Управление списком покупок:", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data == 'add_item')
def add_shopping_item_callback(call):
    USER_STATES[call.from_user.id] = {'action': 'add_item', 'step': 'item'}
    bot.send_message(call.message.chat.id, "Введите название товара:")


@bot.message_handler(func=lambda m: USER_STATES.get(m.from_user.id, {}).get('step') == 'item')
def process_shopping_item(message):
    user_id = message.from_user.id
    USER_STATES[user_id] = {'action': 'add_item', 'step': 'category', 'item': message.text}
    bot.send_message(message.chat.id, "Введите категорию товара:")


@bot.message_handler(func=lambda m: USER_STATES.get(m.from_user.id, {}).get('step') == 'category')
def process_shopping_category(message):
    user_id = message.from_user.id
    add_shopping_item(user_id, USER_STATES[user_id]['item'], message.text)
    bot.send_message(message.chat.id, "Товар добавлен в список покупок!", reply_markup=get_main_markup())
    del USER_STATES[user_id]


@bot.callback_query_handler(func=lambda call: call.data == 'show_list')
def show_shopping_list(call):
    items = get_shopping_list(call.from_user.id)
    if not items:
        bot.send_message(call.message.chat.id, "Ваш список покупок пуст.")
        return
    
    items_by_category = {}
    for item in items:
        if item[2] not in items_by_category:
            items_by_category[item[2]] = []
        items_by_category[item[2]].append(item[1])
    
    text = "Ваш список покупок:\n\n"
    for category in items_by_category:
        text += f"<b>{category}:</b>\n"
        text += "\n".join(f"• {item}" for item in items_by_category[category])
        text += "\n\n"
    
    bot.send_message(call.message.chat.id, text, parse_mode='HTML')


@bot.callback_query_handler(func=lambda call: call.data == 'delete_item')
def delete_shopping_item_callback(call):
    USER_STATES[call.from_user.id] = {'step': 'delete_item'}
    bot.send_message(call.message.chat.id, "Введите ID товара для удаления:")


@bot.message_handler(func=lambda m: USER_STATES.get(m.from_user.id, {}).get('step') == 'delete_item')
def process_delete_item(message):
    user_id = message.from_user.id
    try:
        item_id = int(message.text)
        delete_shopping_item(item_id)
        bot.send_message(message.chat.id, "Товар удален из списка!", reply_markup=get_main_markup())
    except ValueError:
        bot.send_message(message.chat.id, "Неверный ID. Введите число.")
    finally:
        if user_id in USER_STATES:
            del USER_STATES[user_id]


@bot.message_handler(func=lambda m: m.text == '💡 Предложить функционал')
def suggest_feature(message):
    bot.send_message(message.chat.id, "Ваши предложения по улучшению бота отправляйте разработчику.")


if __name__ == '__main__':
    threading.Thread(target=schedule_checker, args=(bot,), daemon=True).start()
    bot.infinity_polling()
