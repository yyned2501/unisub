"""日志模块 — 控制台 + 文件输出，按天轮转，保留 30 天。"""

import logging
import os
from logging.handlers import TimedRotatingFileHandler


def init_logger(debug: bool = False) -> logging.Logger:
    """初始化应用日志器，同时输出到控制台和按天轮转的文件。

    文件存放在 logs/ 目录下，每天午夜轮转，最多保留 30 个备份。
    重复调用返回同一个已配置的 logger 实例。

    Args:
        debug: True 时将 logger 和控制台 handler 级别设为 DEBUG

    Returns:
        配置完成的 logging.Logger 实例
    """
    logger = logging.getLogger("unisub")
    logger.setLevel(logging.DEBUG if debug else logging.INFO)

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    # 控制台 handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG if debug else logging.INFO)
    console_fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_fmt)
    logger.addHandler(console_handler)

    # 文件 handler — 按天轮转，保留 30 天
    os.makedirs("logs", exist_ok=True)
    file_handler = TimedRotatingFileHandler(
        filename="logs/unisub.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_fmt)
    logger.addHandler(file_handler)

    return logger
