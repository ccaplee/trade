# strategy.py - 매매 전략 로직 (MA 골든크로스 + RSI 과매도 반등)

import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

import config

logger = logging.getLogger(__name__)


class Signal(Enum):
    BUY = auto()
    SELL_PROFIT = auto()   # 익절
    SELL_LOSS = auto()     # 손절
    SELL_EOD = auto()      # 장 마감 강제 청산
    HOLD = auto()


@dataclass
class Position:
    """보유 포지션 정보."""
    ticker: str
    qty: int
    avg_price: float
    entry_time: str = ""


@dataclass
class StrategyState:
    """종목별 전략 상태 (이전 MA 관계 기억용)."""
    prev_ma_short: Optional[float] = None
    prev_ma_long: Optional[float] = None


# ── 지표 계산 ────────────────────────────────────────────────────────────────────

def _closing_prices(candles: list[dict]) -> list[float]:
    """캔들 리스트에서 종가 리스트를 추출합니다 (오래된 순)."""
    return [c["close"] for c in reversed(candles)]


def calc_ma(prices: list[float], period: int) -> Optional[float]:
    """단순 이동평균(SMA) 계산. 데이터 부족 시 None 반환."""
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period


def calc_rsi(prices: list[float], period: int = 14) -> Optional[float]:
    """RSI(Relative Strength Index) 계산. 데이터 부족 시 None 반환.

    Wilder 방식의 지수이동평균(SMMA)을 사용합니다.
    """
    if len(prices) < period + 1:
        return None

    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gains = [d if d > 0 else 0.0 for d in deltas]
    losses = [abs(d) if d < 0 else 0.0 for d in deltas]

    # 초기 평균 (단순 평균)
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    # Wilder SMMA
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1 + rs))


# ── 신호 생성 ────────────────────────────────────────────────────────────────────

def generate_signal(
    ticker: str,
    candles: list[dict],
    position: Optional[Position],
    state: StrategyState,
) -> Signal:
    """매수/매도/보유 신호를 생성합니다.

    매수 조건 (둘 중 하나 충족):
      1. MA5가 MA20을 상향 돌파 (골든크로스)
      2. RSI가 RSI_OVERSOLD 이하에서 반등

    매도 조건 (포지션 보유 시):
      - 수익률 >= TAKE_PROFIT_RATE → 익절
      - 손실률 >= STOP_LOSS_RATE   → 손절
    """
    if not candles:
        return Signal.HOLD

    prices = _closing_prices(candles)
    current_price = prices[-1]

    ma_short = calc_ma(prices, config.MA_SHORT)
    ma_long = calc_ma(prices, config.MA_LONG)
    rsi = calc_rsi(prices, config.RSI_PERIOD)

    logger.debug(
        "[%s] price=%.0f MA5=%.1f MA20=%.1f RSI=%.1f",
        ticker,
        current_price,
        ma_short or 0,
        ma_long or 0,
        rsi or 0,
    )

    # ── 매도 판단 (포지션 보유 중) ──────────────────────────────────────────────
    if position is not None:
        pnl_rate = (current_price - position.avg_price) / position.avg_price
        if pnl_rate >= config.TAKE_PROFIT_RATE:
            logger.info("[%s] 익절 신호: 수익률 %.2f%%", ticker, pnl_rate * 100)
            return Signal.SELL_PROFIT
        if pnl_rate <= -config.STOP_LOSS_RATE:
            logger.info("[%s] 손절 신호: 손실률 %.2f%%", ticker, pnl_rate * 100)
            return Signal.SELL_LOSS

    # ── 매수 판단 (포지션 없을 때) ──────────────────────────────────────────────
    if position is None:
        golden_cross = False
        rsi_bounce = False

        # 골든크로스: 이전에 MA5 < MA20 이었다가 현재 MA5 >= MA20
        if ma_short is not None and ma_long is not None:
            if (
                state.prev_ma_short is not None
                and state.prev_ma_long is not None
                and state.prev_ma_short < state.prev_ma_long
                and ma_short >= ma_long
            ):
                golden_cross = True

        # RSI 과매도 반등: RSI가 이전에 RSI_OVERSOLD 이하였다가 현재 상승
        if rsi is not None:
            prev_rsi = _calc_prev_rsi(prices, config.RSI_PERIOD)
            if prev_rsi is not None and prev_rsi <= config.RSI_OVERSOLD and rsi > prev_rsi:
                rsi_bounce = True

        if golden_cross or rsi_bounce:
            reason = []
            if golden_cross:
                reason.append("골든크로스")
            if rsi_bounce:
                reason.append(f"RSI 과매도 반등({rsi:.1f})")
            logger.info("[%s] 매수 신호: %s", ticker, ", ".join(reason))
            return Signal.BUY

    # 상태 업데이트
    state.prev_ma_short = ma_short
    state.prev_ma_long = ma_long

    return Signal.HOLD


def _calc_prev_rsi(prices: list[float], period: int) -> Optional[float]:
    """한 봉 이전의 RSI 값을 계산합니다."""
    if len(prices) < 2:
        return None
    return calc_rsi(prices[:-1], period)


# ── 주문 수량 계산 ────────────────────────────────────────────────────────────────

def calc_order_qty(cash: float, current_price: float) -> int:
    """종목당 최대 투자 한도 내에서 매수 가능한 수량을 계산합니다.

    Args:
        cash: 주문 가능 예수금
        current_price: 현재가

    Returns:
        매수 수량 (0이면 매수 불가)
    """
    if current_price <= 0:
        return 0
    invest_amount = cash * config.MAX_POSITION_RATIO
    qty = int(invest_amount // current_price)
    return qty
