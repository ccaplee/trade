"""
main.py – KIS ETF 단타 자동매매 진입점

실행 방법:
    python main.py

장 시작(09:00) 직후 ETF 를 선별하고,
POLL_INTERVAL_SEC 간격으로 매매 사이클을 반복합니다.
MARKET_CLOSE_TIME 도달 시 전체 포지션을 청산하고 종료합니다.
"""

from __future__ import annotations

import logging
import signal
import sys
import time
from datetime import datetime

import config
from kis_api import KISClient
from trader import ETFTrader


# ── 로거 설정 ──────────────────────────────────────────────────────────────────

def _setup_logging() -> None:
    fmt = "%(asctime)s [%(levelname)s] %(name)s – %(message)s"
    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(config.LOG_FILE, encoding="utf-8"),
    ]
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
        format=fmt,
        handlers=handlers,
    )


# ── 시간 유틸 ──────────────────────────────────────────────────────────────────

def _parse_hhmm(hhmm: str) -> tuple[int, int]:
    h, m = hhmm.split(":")
    return int(h), int(m)


def _is_market_open() -> bool:
    now = datetime.now()
    oh, om = _parse_hhmm(config.MARKET_OPEN_TIME)
    ch, cm = _parse_hhmm(config.MARKET_CLOSE_TIME)
    open_min = oh * 60 + om
    close_min = ch * 60 + cm
    now_min = now.hour * 60 + now.minute
    return open_min <= now_min < close_min


def _is_market_closed() -> bool:
    now = datetime.now()
    ch, cm = _parse_hhmm(config.MARKET_CLOSE_TIME)
    close_min = ch * 60 + cm
    now_min = now.hour * 60 + now.minute
    return now_min >= close_min


def _wait_for_market_open() -> None:
    """장 시작 시각까지 대기한다."""
    logger = logging.getLogger(__name__)
    while not _is_market_open():
        now = datetime.now()
        logger.info("장 대기 중... 현재 시각: %s", now.strftime("%H:%M:%S"))
        time.sleep(30)


# ── 메인 루프 ──────────────────────────────────────────────────────────────────

def main() -> None:
    _setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("========== KIS ETF 단타 자동매매 시작 ==========")

    client = KISClient()
    trader = ETFTrader(client)

    # Graceful shutdown 처리 (Ctrl+C, SIGTERM)
    _shutdown = False

    def _handle_signal(signum: int, frame: object) -> None:
        nonlocal _shutdown
        logger.info("종료 신호 수신 (%s). 다음 사이클 후 청산합니다.", signal.Signals(signum).name)
        _shutdown = True

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    # 장 대기
    if not _is_market_open():
        _wait_for_market_open()

    # 장 시작 직후 ETF 선별
    logger.info("장 개시 후 ETF 선별 실행")
    try:
        trader.select_etfs()
    except Exception as exc:
        logger.error("ETF 선별 실패: %s", exc)

    # 메인 매매 루프
    while not _shutdown:
        if _is_market_closed():
            logger.info("장 마감 시각 도달. 전체 포지션 청산 후 종료합니다.")
            try:
                trader.close_all_positions()
            except Exception as exc:
                logger.error("장 마감 청산 실패: %s", exc)
            break

        if not _is_market_open():
            logger.info("장 외 시간. 대기 중...")
            time.sleep(60)
            continue

        try:
            trader.run_cycle()
        except Exception as exc:
            logger.error("매매 사이클 오류: %s", exc)

        if _shutdown:
            break

        time.sleep(config.POLL_INTERVAL_SEC)

    logger.info("========== 자동매매 종료 ==========")


if __name__ == "__main__":
    main()
