"""
메인 트레이더 모듈
장 시작 ~ 종료 시간 동안 전략 루프를 실행합니다.

흐름:
  1. 장 시작 후 ETF 선별
  2. 매 LOOP_INTERVAL_SEC 초마다:
     a. 보유 종목 → 매도 조건 확인
     b. 미보유 선별 종목 → 매수 조건 확인
  3. 장 종료 직전 전체 보유 청산
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, time as dtime

import config
from etf_selector import select_top_etfs
from kis_api import KISClient
from strategy import check_buy_signal, check_sell_signal

logger = logging.getLogger(__name__)


@dataclass
class Position:
    ticker: str
    qty: int
    avg_price: float
    buy_time: datetime = field(default_factory=datetime.now)


class Trader:
    def __init__(self) -> None:
        self._client = KISClient()
        self._positions: dict[str, Position] = {}   # ticker → Position
        self._watch_list: list[str] = []

    # ── 시간 유틸 ──────────────────────────────────────────────────────────────

    @staticmethod
    def _now_time() -> dtime:
        return datetime.now().time()

    @staticmethod
    def _parse_time(t: str) -> dtime:
        h, m = map(int, t.split(":"))
        return dtime(h, m)

    def _is_market_open(self) -> bool:
        now = self._now_time()
        return (
            self._parse_time(config.MARKET_OPEN)
            <= now
            < self._parse_time(config.MARKET_CLOSE)
        )

    # ── 현재가 조회 ────────────────────────────────────────────────────────────

    def _get_current_price(self, ticker: str) -> float | None:
        try:
            data = self._client.get_price(ticker)
            output = data.get("output", {})
            return float(output.get("stck_prpr", 0))
        except Exception as exc:
            logger.warning("[%s] 현재가 조회 실패: %s", ticker, exc)
            return None

    # ── 분봉 조회 ──────────────────────────────────────────────────────────────

    def _get_candles(self, ticker: str) -> list:
        try:
            return self._client.get_minute_candles(ticker, config.CANDLE_INTERVAL_MIN)
        except Exception as exc:
            logger.warning("[%s] 분봉 조회 실패: %s", ticker, exc)
            return []

    # ── 매수 처리 ──────────────────────────────────────────────────────────────

    def _try_buy(self, ticker: str) -> None:
        if ticker in self._positions:
            return  # 이미 보유 중

        candles = self._get_candles(ticker)
        if not check_buy_signal(candles):
            return

        current_price = self._get_current_price(ticker)
        if current_price is None or current_price <= 0:
            logger.warning("[%s] 현재가 조회 실패로 매수 건너뜀", ticker)
            return

        try:
            self._client.buy_market(ticker, config.ORDER_QUANTITY)
            self._positions[ticker] = Position(
                ticker=ticker,
                qty=config.ORDER_QUANTITY,
                avg_price=current_price,
            )
            logger.info(
                "[%s] 매수 완료 | 수량=%d | 현재가=%.0f",
                ticker,
                config.ORDER_QUANTITY,
                current_price,
            )
        except Exception as exc:
            logger.error("[%s] 매수 주문 오류: %s", ticker, exc)

    # ── 매도 처리 ──────────────────────────────────────────────────────────────

    def _try_sell(self, ticker: str, force: bool = False) -> None:
        pos = self._positions.get(ticker)
        if pos is None:
            return

        current_price = self._get_current_price(ticker)
        if current_price is None or current_price <= 0:
            logger.warning("[%s] 현재가 조회 실패로 매도 건너뜀", ticker)
            return

        if force:
            reason = "장 종료 강제 청산"
        else:
            should_sell, reason = check_sell_signal(pos.avg_price, current_price)
            if not should_sell:
                return

        try:
            self._client.sell_market(ticker, pos.qty)
            pnl = (current_price - pos.avg_price) * pos.qty
            logger.info(
                "[%s] 매도 완료 | 수량=%d | 매수가=%.0f | 현재가=%.0f | 손익=%.0f원 | 사유=%s",
                ticker,
                pos.qty,
                pos.avg_price,
                current_price,
                pnl,
                reason,
            )
            del self._positions[ticker]
        except Exception as exc:
            logger.error("[%s] 매도 주문 오류: %s", ticker, exc)

    # ── 메인 루프 ──────────────────────────────────────────────────────────────

    def run(self) -> None:
        logger.info("=== ETF 자동매매 시작 ===")
        logger.info(
            "계좌: %s | 모의투자: %s | 장시간: %s ~ %s",
            config.ACCOUNT_NO,
            config.IS_PAPER,
            config.MARKET_OPEN,
            config.MARKET_CLOSE,
        )

        # 장 시작 대기
        open_time = self._parse_time(config.MARKET_OPEN)
        while self._now_time() < open_time:
            wait_sec = (
                datetime.combine(datetime.today(), open_time)
                - datetime.now()
            ).total_seconds()
            if wait_sec <= 0:
                break
            logger.info("장 시작 대기 중... (%d초 후)", int(wait_sec))
            time.sleep(min(wait_sec, 60))

        # ETF 선별 (장 시작 직후 1회)
        logger.info("장 시작 – ETF 선별 중...")
        self._watch_list = select_top_etfs(self._client)
        logger.info("감시 종목: %s", self._watch_list)

        # 전략 루프
        close_time = self._parse_time(config.MARKET_CLOSE)
        while self._now_time() < close_time:
            loop_start = time.monotonic()
            logger.debug("--- 전략 루프 시작 ---")

            # 1) 보유 종목 매도 검토
            for ticker in list(self._positions.keys()):
                self._try_sell(ticker)

            # 2) 감시 종목 매수 검토
            for ticker in self._watch_list:
                if ticker not in self._positions:
                    self._try_buy(ticker)

            elapsed = time.monotonic() - loop_start
            sleep_time = max(0, config.LOOP_INTERVAL_SEC - elapsed)
            time.sleep(sleep_time)

        # 장 종료 – 전체 청산
        logger.info("장 종료 – 보유 종목 전체 청산")
        for ticker in list(self._positions.keys()):
            self._try_sell(ticker, force=True)

        logger.info("=== ETF 자동매매 종료 ===")
