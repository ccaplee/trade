"""
trader.py – ETF 단타 자동매매 전략 엔진

전략 요약:
  매수: MA5 > MA20 골든크로스  OR  RSI < RSI_OVERSOLD 에서 반등
  매도: 수익률 >= +1.5% (익절)  OR  수익률 <= -0.8% (손절)
  리스크: 종목당 최대 잔고의 20%, 동시 보유 최대 3종목
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime

import config
from kis_api import Candle, KISClient, Position, Quote

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 기술 지표 계산 유틸
# ─────────────────────────────────────────────────────────────────────────────

def _moving_average(closes: list[float], period: int) -> float | None:
    """단순 이동평균 계산. 데이터가 부족하면 None 반환."""
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def _rsi(closes: list[float], period: int = config.RSI_PERIOD) -> float | None:
    """RSI 계산 (Wilder 평활화 방식). 데이터가 부족하면 None 반환."""
    if len(closes) < period + 1:
        return None
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


# ─────────────────────────────────────────────────────────────────────────────
# 매매 신호
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Signal:
    code: str
    action: str          # "BUY" | "SELL" | "HOLD"
    reason: str = ""
    current_price: float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# 트레이더 메인 클래스
# ─────────────────────────────────────────────────────────────────────────────

class ETFTrader:
    """
    ETF 단타 자동매매 전략을 실행하는 핵심 클래스.

    외부에서는 `run_cycle()` 을 주기적으로 호출하면 됩니다.
    """

    def __init__(self, client: KISClient) -> None:
        self.client = client
        # 감시 대상 ETF 코드 (장 시작 후 선별)
        self._watched: list[str] = []
        # 전 주기 RSI 값 저장 (반등 감지용): {code: prev_rsi}
        self._prev_rsi: dict[str, float] = {}

    # ── 공개 인터페이스 ───────────────────────────────────────────────────────

    def select_etfs(self) -> None:
        """거래량×변동성 기준 상위 N개 ETF 를 감시 목록으로 선별한다."""
        logger.info("ETF 선별 시작 (유니버스 %d개)", len(config.ETF_UNIVERSE))
        ranked = self.client.get_etf_ranking(config.ETF_UNIVERSE)
        self._watched = [code for code, _ in ranked[: config.TOP_N_ETF]]
        logger.info("선별된 ETF: %s", self._watched)

    def run_cycle(self) -> None:
        """
        한 번의 매매 사이클을 실행한다.

        1. 감시 ETF 가 비어 있으면 선별 먼저 수행
        2. 보유 종목 익절/손절 체크
        3. 신규 매수 신호 체크
        """
        if not self._watched:
            self.select_etfs()

        positions = self.client.get_positions()
        position_map: dict[str, Position] = {p.code: p for p in positions}

        # ── 1) 익절 / 손절 체크 ────────────────────────────────────────────
        for pos in positions:
            signal = self._check_exit_signal(pos)
            if signal.action == "SELL":
                self._execute_sell(pos.code, pos.quantity, signal.reason)

        # 매도 후 포지션 재조회
        positions = self.client.get_positions()
        position_map = {p.code: p for p in positions}

        # ── 2) 신규 매수 신호 체크 ─────────────────────────────────────────
        if len(positions) >= config.MAX_POSITIONS:
            logger.debug("최대 보유 종목 수 도달 (%d). 신규 매수 생략.", config.MAX_POSITIONS)
            return

        for code in self._watched:
            if code in position_map:
                continue   # 이미 보유 중
            signal = self._check_entry_signal(code)
            if signal.action == "BUY":
                balance = self.client.get_balance()
                self._execute_buy(code, signal.current_price, balance, signal.reason)
                # 매수 후 보유 수 재확인
                positions = self.client.get_positions()
                if len(positions) >= config.MAX_POSITIONS:
                    break

    # ── 신호 생성 로직 ────────────────────────────────────────────────────────

    def _check_entry_signal(self, code: str) -> Signal:
        """매수 신호를 판단한다."""
        try:
            candles = self.client.get_candles(code, count=config.MA_LONG + 5)
        except Exception as exc:
            logger.warning("[%s] 캔들 조회 실패: %s", code, exc)
            return Signal(code=code, action="HOLD", reason="캔들 조회 실패")

        if len(candles) < config.MA_LONG + 1:
            return Signal(code=code, action="HOLD", reason="데이터 부족")

        closes = [c.close for c in candles]
        current_price = closes[-1]

        ma_short_now = _moving_average(closes, config.MA_SHORT)
        ma_long_now = _moving_average(closes, config.MA_LONG)
        ma_short_prev = _moving_average(closes[:-1], config.MA_SHORT)
        ma_long_prev = _moving_average(closes[:-1], config.MA_LONG)

        rsi_now = _rsi(closes)
        prev_rsi = self._prev_rsi.get(code)

        reason = ""

        # 조건 1: 골든크로스 (MA5 상향 돌파 MA20)
        if (
            ma_short_now is not None
            and ma_long_now is not None
            and ma_short_prev is not None
            and ma_long_prev is not None
            and ma_short_prev <= ma_long_prev
            and ma_short_now > ma_long_now
        ):
            reason = f"골든크로스 MA{config.MA_SHORT}={ma_short_now:.1f} > MA{config.MA_LONG}={ma_long_now:.1f}"
            logger.info("[%s] 매수 신호: %s", code, reason)
            if rsi_now is not None:
                self._prev_rsi[code] = rsi_now
            return Signal(code=code, action="BUY", reason=reason, current_price=current_price)

        # 조건 2: RSI 과매도 반등
        if (
            rsi_now is not None
            and prev_rsi is not None
            and prev_rsi <= config.RSI_OVERSOLD
            and rsi_now > config.RSI_OVERSOLD
        ):
            reason = f"RSI 반등 {prev_rsi:.1f} → {rsi_now:.1f}"
            logger.info("[%s] 매수 신호: %s", code, reason)
            self._prev_rsi[code] = rsi_now
            return Signal(code=code, action="BUY", reason=reason, current_price=current_price)

        if rsi_now is not None:
            self._prev_rsi[code] = rsi_now

        return Signal(code=code, action="HOLD", current_price=current_price)

    def _check_exit_signal(self, position: Position) -> Signal:
        """익절/손절 조건을 확인하여 매도 신호를 반환한다."""
        try:
            quote = self.client.get_quote(position.code)
            current_price = quote.price
        except Exception as exc:
            logger.warning("[%s] 현재가 조회 실패: %s", position.code, exc)
            current_price = position.current_price

        if position.avg_price <= 0:
            return Signal(code=position.code, action="HOLD")

        profit_rate = (current_price - position.avg_price) / position.avg_price

        if profit_rate >= config.TAKE_PROFIT_RATE:
            reason = f"익절 수익률={profit_rate * 100:.2f}%"
            logger.info("[%s] 매도 신호: %s", position.code, reason)
            return Signal(
                code=position.code, action="SELL", reason=reason, current_price=current_price
            )

        if profit_rate <= -config.STOP_LOSS_RATE:
            reason = f"손절 수익률={profit_rate * 100:.2f}%"
            logger.info("[%s] 매도 신호: %s", position.code, reason)
            return Signal(
                code=position.code, action="SELL", reason=reason, current_price=current_price
            )

        return Signal(code=position.code, action="HOLD", current_price=current_price)

    # ── 주문 실행 ─────────────────────────────────────────────────────────────

    def _execute_buy(
        self, code: str, price: float, balance: float, reason: str
    ) -> None:
        """매수 수량을 계산하고 시장가 매수 주문을 낸다."""
        invest_amount = balance * config.MAX_POSITION_RATIO
        if price <= 0:
            logger.warning("[%s] 가격 정보 없음. 매수 취소.", code)
            return
        quantity = math.floor(invest_amount / price)
        if quantity <= 0:
            logger.warning(
                "[%s] 주문 가능 수량 0. 잔고=%.0f, 가격=%.0f", code, balance, price
            )
            return
        logger.info(
            "[%s] 매수 실행: %d주 × %.0f원 = %.0f원 (%s)",
            code, quantity, price, quantity * price, reason,
        )
        try:
            self.client.buy_market(code, quantity)
        except Exception as exc:
            logger.error("[%s] 매수 주문 실패: %s", code, exc)

    def _execute_sell(self, code: str, quantity: int, reason: str) -> None:
        """시장가 매도 주문을 낸다."""
        logger.info("[%s] 매도 실행: %d주 (%s)", code, quantity, reason)
        try:
            self.client.sell_market(code, quantity)
        except Exception as exc:
            logger.error("[%s] 매도 주문 실패: %s", code, exc)

    # ── 장 마감 청산 ──────────────────────────────────────────────────────────

    def close_all_positions(self) -> None:
        """장 마감 전 전체 포지션을 청산한다."""
        positions = self.client.get_positions()
        if not positions:
            logger.info("청산할 보유 종목 없음.")
            return
        for pos in positions:
            logger.info("[%s] 장 마감 청산: %d주", pos.code, pos.quantity)
            self._execute_sell(pos.code, pos.quantity, "장마감 청산")
