import time
from datetime import datetime, timedelta
import pytz  # type: ignore
from database import DB


def schedule_checker(bot_instance):
    """Основной цикл проверки напоминаний"""
    while True:
        check_reminders(bot_instance)
        time.sleep(3)


def check_reminders(bot_instance):
    """Проверка с учетом часового пояса UTC"""
    try:
        with DB() as cursor:
            now_utc = datetime.now(pytz.utc).replace(tzinfo=None)  # Убираем tzinfo для сравнения

            # Выбираем только активные напоминания
            cursor.execute('''
                SELECT id, user_id, text, datetime, repeat
                FROM reminders
                WHERE is_active = 1
            ''')

            for rem in cursor.fetchall():
                rem_id, user_id, text, dt_str, repeat = rem
                try:
                    dt = datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')

                    # Проверяем с запасом в 5 секунд для компенсации задержек
                    if dt <= now_utc + timedelta(seconds=5):
                        try:
                            # Отправляем напоминание
                            bot_instance.send_message(
                                user_id,
                                f"⏰ Напоминание: {text}\nВремя: {dt.strftime('%H:%M %d.%m.%Y')}"
                            )

                            # Обновляем дату для повторяющихся
                            if repeat:
                                delta = {
                                    'daily': timedelta(days=1),
                                    'weekly': timedelta(weeks=1),
                                    'monthly': timedelta(days=30),
                                    'yearly': timedelta(days=365)
                                }.get(repeat)

                                new_dt = dt + delta
                                cursor.execute(
                                    'UPDATE reminders SET datetime = ? WHERE id = ?',
                                    (new_dt.strftime('%Y-%m-%d %H:%M:%S'), rem_id)
                                )
                            else:
                                cursor.execute(
                                    'UPDATE reminders SET is_active = 0 WHERE id = ?',
                                    (rem_id,)
                                )

                        except Exception as e:
                            print(f"Ошибка отправки: {e}")

                except Exception as e:
                    print(f"Ошибка обработки даты {rem_id}: {e}")

    except Exception as e:
        print(f"Ошибка в check_reminders: {e}")
