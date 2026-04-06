"""
메인 진입점
- 장 시간 판단
- ETF 선별 (장 시작 N분 후)
- 메인 루프: 매수/매도 신호 체크
- 장 종료 전 전량 청산
"""
import logging
import time
from datetime import datetime, time as dtime

import kis_api
import etf_selector
import config
from trader import Trader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── 시간 유틸 ──────────────────────────────────────────────────────────────────

def _parse_hhmm(hhmm: str) -> dtime:
    h, m = map(int, hhmm.split(":"))
    return dtime(h, m)


def _now() -> dtime:
    return datetime.now().time()


def is_market_open() -> bool:
    """현재 시각이 장 운영 시간 내인지 확인합니다."""
    t = _now()
    return _parse_hhmm(config.MARKET_OPEN) <= t <= _parse_hhmm(config.MARKET_CLOSE)


def is_scan_time() -> bool:
    """ETF 스캔을 시작할 수 있는 시각인지 확인합니다."""
    t = _now()
    h, m = map(int, config.MARKET_OPEN.split(":"))
    scan_h, scan_m = divmod(h * 60 + m + config.SCAN_START_OFFSET_MIN, 60)
    return t >= dtime(scan_h, scan_m)


def near_market_close() -> bool:
    """장 종료까지 1분 이내인지 확인합니다."""
    t = _now()
    close = _parse_hhmm(config.MARKET_CLOSE)
    close_min = close.hour * 60 + close.minute
    now_min = t.hour * 60 + t.minute
    return now_min >= close_min - 1


# ── 메인 루프 ──────────────────────────────────────────────────────────────────

def main() -> None:
    logger.info("=== KIS ETF 자동매매 시작 ===")
    logger.info(
        "모드: %s | 계좌: %s-%s",
        "모의투자" if config.IS_PAPER_TRADING else "실전투자",
        config.CANO,
        config.ACNT_PRDT_CD,
    )

    trader = Trader()
    watch_list: list[str] = []

    while True:
        try:
            if not is_market_open():
                logger.info("장 시간 외 대기 중...")
                time.sleep(60)
                continue

            # 장 종료 직전: 전량 청산 후 종료
            if near_market_close():
                logger.info("장 종료 임박 – 전량 청산")
                trader.liquidate_all()
                logger.info("=== 자동매매 종료 ===")
                break

            # 장 시작 후 N분 지나야 ETF 선별
            if not watch_list:
                if is_scan_time():
                    logger.info("ETF 선별 시작...")
                    watch_list = etf_selector.select_top_etfs()
                    if not watch_list:
                        logger.warning("선별된 ETF 없음, 30초 후 재시도")
                        time.sleep(30)
                        continue
                    logger.info("감시 종목: %s", watch_list)
                else:
                    logger.info("ETF 스캔 대기 중 (장 시작 후 %d분 경과 필요)", config.SCAN_START_OFFSET_MIN)
                    time.sleep(30)
                    continue

            # 각 ETF에 대해 매도 → 매수 순서로 체크
            for ticker in watch_list:
                try:
                    # 보유 포지션 매도 조건 확인
                    if trader.has_position(ticker):
                        trader.check_and_sell(ticker)

                    # 미보유 시 매수 조건 확인
                    if not trader.has_position(ticker):
                        candles = kis_api.get_minute_candles(ticker, config.CANDLE_INTERVAL)
                        trader.check_and_buy(ticker, candles)

                    # API 호출 간격 (속도 제한 방지)
                    time.sleep(0.2)

                except Exception as exc:
                    logger.error("[%s] 처리 중 오류: %s", ticker, exc)

        except KeyboardInterrupt:
            logger.info("사용자 중단 – 전량 청산 후 종료")
            trader.liquidate_all()
            break
        except Exception as exc:
            logger.error("메인 루프 오류: %s", exc)

        time.sleep(config.LOOP_INTERVAL_SEC)


if __name__ == "__main__":
    main()
