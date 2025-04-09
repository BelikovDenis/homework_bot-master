import sqlite3
from datetime import datetime


def init_db():
    conn = sqlite3.connect('assistant.db')
    cursor = conn.cursor()

    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            created DATETIME
        )
    ''')

    # Reminders table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            text TEXT,
            datetime DATETIME,
            repeat TEXT,
            is_active BOOLEAN DEFAULT 1,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
    ''')

    # Shopping list with categories
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS shopping_list (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            item TEXT,
            category TEXT,
            created DATETIME,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
    ''')

    conn.commit()
    conn.close()


class DB:
    def __enter__(self):
        self.conn = sqlite3.connect('assistant.db')
        return self.conn.cursor()

    def __exit__(self, type, value, traceback):
        self.conn.commit()
        self.conn.close()


def add_reminder(user_id, text, dt, repeat=None):
    with DB() as cursor:
        cursor.execute('''
            INSERT INTO reminders 
            (user_id, text, datetime, repeat)
            VALUES (?, ?, ?, ?)
        ''', (user_id, text, dt, repeat))


def get_reminders(user_id):
    with DB() as cursor:
        cursor.execute('''
            SELECT id, text, datetime, repeat 
            FROM reminders 
            WHERE user_id = ? AND is_active = 1
            ORDER BY datetime
        ''', (user_id,))
        return cursor.fetchall()


def delete_reminder(rem_id):
    with DB() as cursor:
        cursor.execute('DELETE FROM reminders WHERE id = ?', (rem_id,))


def get_shopping_list(user_id):
    with DB() as cursor:
        cursor.execute('''
            SELECT id, item, category 
            FROM shopping_list 
            WHERE user_id = ?
            ORDER BY category, item
        ''', (user_id,))
        return cursor.fetchall()


def add_shopping_item(user_id, item, category):
    with DB() as cursor:
        cursor.execute('''
            INSERT INTO shopping_list 
            (user_id, item, category, created)
            VALUES (?, ?, ?, ?)
        ''', (user_id, item, category, datetime.now()))


def delete_shopping_item(item_id):
    with DB() as cursor:
        cursor.execute('DELETE FROM shopping_list WHERE id = ?', (item_id,))
