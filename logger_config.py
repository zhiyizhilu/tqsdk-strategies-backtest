#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
日志配置模块
==========

提供统一的日志配置，支持按调用类型和时间命名日志文件
"""

import logging
import os
from datetime import datetime


def setup_logger(name: str, log_dir: str = None) -> logging.Logger:
    """
    配置并返回日志记录器

    Args:
        name: 日志名称（同时也作为日志文件的类型标识）
        log_dir: 日志目录，默认为调用文件所在目录的 log 子目录

    Returns:
        logging.Logger: 配置好的日志记录器
    """
    if log_dir is None:
        import inspect
        caller_frame = inspect.stack()[1]
        caller_file = caller_frame.filename
        log_dir = os.path.join(
            os.path.dirname(os.path.abspath(caller_file)),
            "log"
        )

    os.makedirs(log_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"{name}_{timestamp}.log"
    log_filepath = os.path.join(log_dir, log_filename)

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    if logger.handlers:
        logger.handlers.clear()

    file_handler = logging.FileHandler(log_filepath, encoding="utf-8")
    file_handler.setLevel(logging.INFO)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger
