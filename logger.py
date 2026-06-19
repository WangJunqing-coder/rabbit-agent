"""
日志系统 - 统一的日志配置
"""
import logging
import sys
from pathlib import Path


def setup_logger(
    name: str = "rabbit_agent",
    level: int = logging.INFO,
    log_file: str = None
) -> logging.Logger:
    """
    配置并返回 logger

    Args:
        name: logger 名称
        level: 日志级别
        log_file: 日志文件路径（可选）
    """
    logger = logging.getLogger(name)

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    logger.setLevel(level)

    # 格式
    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S"
    )

    # 控制台 handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 文件 handler（可选）
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


# 默认 logger
logger = setup_logger()
