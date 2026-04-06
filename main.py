"""
메인 진입점 - 스케줄러 및 장 운영 시간 관리
"""
import logging
import os
import sys
import time
from datetime import datetime

import schedule

import config
from etf_selector import select_top_etfs
from trader import Trader

# ─── 로깅 설정 ────────────────────────────────────────────────

log_dir = os.path.dirname(config.LOG_FILE)
if log_dir:
    os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(config.LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


def is_market_open() -> bool:
    """현재 시각이 장 운영 시간인지 확인합니다."""
    now = datetime.now()
    # 주말 제외
    if now.weekday() >= 5:
        return False
    t = now.strftime("%H:%M")
    return config.MARKET_OPEN <= t <= config.MARKET_CLOSE


def is_force_sell_time() -> bool:
    """강제 청산 시각 도달 여부를 확인합니다."""
    t = datetime.now().strftime("%H:%M")
    return t >= config.FORCE_SELL_TIME


def run_select_etfs(trader: Trader) -> None:
    """ETF 선정 태스크"""
    if not is_market_open():
        logger.info("장 운영 시간 외 - ETF 선정 건너뜀")
        return
    logger.info("▶ ETF 선정 시작")
    try:
        etfs = select_top_etfs(config.ETF_SELECT_COUNT)
        trader.set_watchlist(etfs)
    except Exception as exc:
        logger.error("ETF 선정 중 오류: %s", exc, exc_info=True)


def run_scan(trader: Trader) -> None:
    """매매 신호 점검 태스크"""
    if not is_market_open():
        return
    force = is_force_sell_time()
    try:
        trader.scan_once(force_sell=force)
    except Exception as exc:
        logger.error("스캔 중 오류: %s", exc, exc_info=True)


def main() -> None:
    logger.info("=" * 60)
    logger.info("KIS ETF 자동매매 프로그램 시작")
    logger.info("  환경: %s", "모의투자" if config.IS_PAPER else "실전투자")
    logger.info("  계좌: %s-%s", config.ACCOUNT_NO, config.ACCOUNT_PRODUCT_CODE)
    logger.info("  목표 수익률: %.1f%%  /  손절: %.1f%%", config.TARGET_PROFIT_RATE * 100, config.STOP_LOSS_RATE * 100)
    logger.info("=" * 60)

    trader = Trader()

    # ─── 스케줄 등록 ─────────────────────────────────────────
    # ETF 선정: 장 시작 직후 1회 + 30분마다 재선정
    schedule.every().day.at(config.ETF_SELECT_TIME).do(run_select_etfs, trader)
    schedule.every(30).minutes.do(run_select_etfs, trader)

    # 매매 신호 점검: SCAN_INTERVAL_SECONDS 주기
    schedule.every(config.SCAN_INTERVAL_SECONDS).seconds.do(run_scan, trader)

    # 장 마감 후 요약 출력
    schedule.every().day.at("15:31").do(trader.print_summary)

    logger.info(
        "스케줄 등록 완료. ETF 선정: %s, 스캔 주기: %d초",
        config.ETF_SELECT_TIME,
        config.SCAN_INTERVAL_SECONDS,
    )

    # 장 시작 전에 프로그램을 켜뒀을 경우, 장 열리면 즉시 ETF 선정
    if is_market_open():
        run_select_etfs(trader)

    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("사용자 중단 요청")
        if trader.positions:
            logger.info("보유 포지션 강제 청산 중...")
            trader.sell_all(reason="프로그램 종료")
        trader.print_summary()
        logger.info("프로그램 종료")


if __name__ == "__main__":
    main()
