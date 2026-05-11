import os
from datetime import datetime
from zoneinfo import ZoneInfo


APP_TIMEZONE = ZoneInfo(os.getenv("APP_TIMEZONE", "Asia/Kolkata"))


def now_local():
    return datetime.now(APP_TIMEZONE)


def today_local():
    return now_local().date()


def timestamp_local():
    return now_local().isoformat(timespec="seconds")
