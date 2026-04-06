"""
주문 실행 및 포지션 관리 모듈
- 매수/매도 주문 실행
- 포지션 추적 (ticker → buy_price, qty)
- 익절 / 손절 로직
"""
import logging
from dataclasses import dataclass, field
from typing import Any

import kis_api
import strategy
import config

logger = logging.getLogger(__name__)


@dataclass
class Position:
    ticker: str
    buy_price: float
    qty: int
    buy_amount: float = field(init=False)

    def __post_init__(self) -> None:
        self.buy_amount = self.buy_price * self.qty


class Trader:
    """포지션 관리 및 주문 실행을 담당합니다."""

    def __init__(self) -> None:
        # ticker → Position
        self._positions: dict[str, Position] = {}

    # ── 공개 인터페이스 ────────────────────────────────────────────────────────

    def has_position(self, ticker: str) -> bool:
        return ticker in self._positions

    def get_position(self, ticker: str) -> Position | None:
        return self._positions.get(ticker)

    def check_and_buy(self, ticker: str, candles: list[dict[str, Any]]) -> None:
        """분봉 데이터를 분석하여 매수 조건 충족 시 주문합니다."""
        if self.has_position(ticker):
            return  # 이미 보유 중이면 추가 매수 안 함

        prices = strategy.parse_candle_closes(candles)
        signal, reason = strategy.should_buy(prices)

        if not signal:
            logger.debug("[%s] 매수 신호 없음: %s", ticker, reason)
            return

        # 현재가 조회
        current_price = self._fetch_current_price(ticker)
        if current_price <= 0:
            logger.warning("[%s] 현재가 조회 실패, 매수 건너뜀", ticker)
            return

        qty = config.ORDER_AMOUNT_KRW // int(current_price)
        if qty <= 0:
            logger.warning("[%s] 주문 금액(%d원)이 현재가(%d원)보다 작아 매수 건너뜀", ticker, config.ORDER_AMOUNT_KRW, current_price)
            return
        logger.info("[%s] 매수 신호 → %s | 현재가=%d 수량=%d", ticker, reason, current_price, qty)

        result = kis_api.place_order(ticker, qty, 0, "buy")  # 시장가 매수
        if result.get("rt_cd") == "0":
            self._positions[ticker] = Position(ticker=ticker, buy_price=current_price, qty=qty)
            logger.info("[%s] 매수 완료: 단가=%d 수량=%d", ticker, current_price, qty)
        else:
            logger.error("[%s] 매수 주문 실패: %s", ticker, result)

    def check_and_sell(self, ticker: str) -> None:
        """보유 포지션에 대해 익절/손절 조건을 확인하고 매도합니다."""
        position = self._positions.get(ticker)
        if position is None:
            return

        current_price = self._fetch_current_price(ticker)
        if current_price <= 0:
            logger.warning("[%s] 현재가 조회 실패, 매도 건너뜀", ticker)
            return

        signal, reason = strategy.should_sell(position.buy_price, current_price)

        if not signal:
            logger.debug("[%s] 매도 신호 없음: %s", ticker, reason)
            return

        logger.info("[%s] 매도 신호 → %s | 현재가=%d", ticker, reason, current_price)

        result = kis_api.place_order(ticker, position.qty, 0, "sell")  # 시장가 매도
        if result.get("rt_cd") == "0":
            pnl = (current_price - position.buy_price) * position.qty
            logger.info(
                "[%s] 매도 완료: 단가=%d 수량=%d PnL=%.0f원",
                ticker,
                current_price,
                position.qty,
                pnl,
            )
            del self._positions[ticker]
        else:
            logger.error("[%s] 매도 주문 실패: %s", ticker, result)

    def liquidate_all(self) -> None:
        """장 종료 전 모든 보유 포지션을 시장가로 청산합니다."""
        tickers = list(self._positions.keys())
        if not tickers:
            return
        logger.info("장 종료 전 전량 청산 시작: %s", tickers)
        for ticker in tickers:
            position = self._positions[ticker]
            result = kis_api.place_order(ticker, position.qty, 0, "sell")
            if result.get("rt_cd") == "0":
                logger.info("[%s] 강제 청산 완료", ticker)
                del self._positions[ticker]
            else:
                logger.error("[%s] 강제 청산 실패: %s", ticker, result)

    # ── 내부 헬퍼 ─────────────────────────────────────────────────────────────

    def _fetch_current_price(self, ticker: str) -> float:
        try:
            data = kis_api.get_etf_price(ticker)
            output = data.get("output", {})
            price_str = output.get("stck_prpr") or output.get("stck_prdy_clpr", "0")
            return float(price_str)
        except Exception as exc:
            logger.error("[%s] 현재가 조회 오류: %s", ticker, exc)
            return 0.0
