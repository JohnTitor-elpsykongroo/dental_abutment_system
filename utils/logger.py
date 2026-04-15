# utils/logger.py
from datetime import datetime


def make_log(message: str, level: str = "INFO") -> str:
    time_str = datetime.now().strftime("%H:%M:%S")
    return "[{}] [{}] {}".format(time_str, level, message)