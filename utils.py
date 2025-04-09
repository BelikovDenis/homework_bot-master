import time
from datetime import datetime, timedelta
from database import DB


def schedule_checker(bot_instance):
    while True:
        check_reminders(bot_instance)
        time.sleep(3)


def check_reminders(bot_instance):
    try:
        with DB() as cursor:
            now = datetime.now()
            cursor.execute(
                'SELECT * FROM reminders WHERE datetime <= ? AND is_active = 1',
                (now,))
            reminders = cursor.fetchall()

            for reminder in reminders:
                user_id = reminder[1]
                text = reminder[2]
                repeat = reminder[4]

                try:
                    bot_instance.send_message(
                        user_id,
                        f"⏰ Напоминание: {text}\nВремя: "
                        f"{reminder[3].strftime('%H:%M %d.%m.%Y')}")
                    
                    if repeat == 'daily':
                        new_dt = reminder[3] + timedelta(days=1)
                    elif repeat == 'weekly':
                        new_dt = reminder[3] + timedelta(weeks=1)
                    elif repeat == 'monthly':
                        new_dt = reminder[3] + timedelta(days=30)
                    elif repeat == 'yearly':
                        new_dt = reminder[3] + timedelta(days=365)
                    else:
                        new_dt = None
                    
                    if new_dt:
                        cursor.execute(
                            'UPDATE reminders SET datetime = ? WHERE id = ?',
                            (new_dt, reminder[0]))
                    else:
                        cursor.execute(
                            'UPDATE reminders SET is_active = 0 WHERE id = ?',
                            (reminder[0],))
                except Exception as e:
                    print(f"Ошибка отправки напоминания: {str(e)}")
    except Exception as e:
        print(f"Ошибка в check_reminders: {str(e)}")
