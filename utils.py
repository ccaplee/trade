"""
utils.py
────────
공통 유틸리티 (로깅 설정, 시간 검사 등)
"""

import logging
import sys
from datetime import datetime, time
from zoneinfo import ZoneInfo

import config

KST = ZoneInfo("Asia/Seoul")


def setup_logger(name: str = "trader") -> logging.Logger:
    """콘솔 + 파일(trader.log) 핸들러를 갖는 로거를 반환합니다."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 콘솔
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    # 파일
    fh = logging.FileHandler("trader.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    logger.addHandler(ch)
    logger.addHandler(fh)
    return logger


def now_kst() -> datetime:
    return datetime.now(tz=KST)


def _parse_hhmm(hhmm: str) -> time:
    h, m = hhmm.split(":")
    return time(int(h), int(m))


def is_market_open() -> bool:
    """현재 KST 시각이 장 운영 시간(09:00~15:30) 내인지 확인합니다."""
    now = now_kst().time()
    open_t = _parse_hhmm(config.MARKET_OPEN_TIME)
    close_t = _parse_hhmm(config.MARKET_CLOSE_TIME)
    # 평일 여부 확인 (0=월 … 4=금)
    weekday = now_kst().weekday()
    if weekday >= 5:
        return False
    return open_t <= now <= close_t


def is_force_sell_time() -> bool:
    """강제 청산 시각 이후인지 확인합니다."""
    now = now_kst().time()
    force_t = _parse_hhmm(config.FORCE_SELL_TIME)
    return now >= force_t
