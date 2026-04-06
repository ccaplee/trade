"""
strategy.py
───────────
단타 매매 전략 모듈

전략 개요
  1. 분봉 데이터를 받아 RSI 와 단기/장기 이동평균을 계산합니다.
  2. 매수 조건: RSI ≤ RSI_BUY_THRESHOLD  AND  단기MA > 장기MA (골든크로스)
  3. 매도 조건: RSI ≥ RSI_SELL_THRESHOLD  OR   단기MA < 장기MA (데드크로스)
  4. 보유 포지션에 대해 목표수익률 / 손절률 도달 시 즉시 매도 신호
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

import config
from utils import setup_logger

logger = setup_logger()


class Signal(Enum):
    BUY = auto()
    SELL = auto()
    HOLD = auto()


@dataclass
class Position:
    symbol: str
    qty: int
    avg_price: float
    name: str = ""


@dataclass
class StrategyState:
    """종목별 전략 상태 (포지션 등)"""
    positions: dict[str, Position] = field(default_factory=dict)


def _compute_rsi(closes: list[float], period: int) -> float:
    """
    Wilder's RSI(period) 를 계산합니다.
    closes: 오래된 순서 → 최신 순서
    """
    if len(closes) < period + 1:
        return 50.0  # 데이터 부족 시 중립값 반환

    # 초기 평균: 인덱스 0..period 사이의 period 개 차이값
    gains, losses = [], []
    for i in range(1, period + 1):
        diff = closes[i] - closes[i - 1]
        (gains if diff >= 0 else losses).append(abs(diff))

    avg_gain = sum(gains) / period if gains else 0.0
    avg_loss = sum(losses) / period if losses else 0.0

    # Wilder's smoothing: 나머지 데이터 포인트에 적용
    for i in range(period + 1, len(closes)):
        diff = closes[i] - closes[i - 1]
        g = diff if diff > 0 else 0.0
        l_ = -diff if diff < 0 else 0.0
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l_) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _compute_ma(closes: list[float], period: int) -> float:
    """단순 이동평균(SMA) 계산"""
    if len(closes) < period:
        return closes[-1] if closes else 0.0
    return sum(closes[-period:]) / period


def _parse_chart_closes(raw_bars: list[dict[str, Any]]) -> list[float]:
    """
    get_minute_chart() 결과(최신→과거)를 받아
    오래된 → 최신 순서의 종가 리스트로 변환합니다.
    """
    closes = []
    for bar in reversed(raw_bars):
        try:
            closes.append(float(bar["stck_prpr"]))
        except (KeyError, ValueError):
            continue
    return closes


def evaluate(
    symbol: str,
    raw_bars: list[dict[str, Any]],
    state: StrategyState,
    current_price: int,
) -> Signal:
    """
    종목 한 개에 대한 매매 신호를 반환합니다.

    Parameters
    ----------
    symbol        : 종목코드
    raw_bars      : kis_api.get_minute_chart() 반환값
    state         : 전략 상태 (포지션 정보 포함)
    current_price : 현재가

    Returns
    -------
    Signal.BUY / Signal.SELL / Signal.HOLD
    """
    closes = _parse_chart_closes(raw_bars)
    if len(closes) < max(config.RSI_PERIOD, config.LONG_MA) + 1:
        logger.debug("[%s] 분봉 데이터 부족 (%d개) → HOLD", symbol, len(closes))
        return Signal.HOLD

    rsi = _compute_rsi(closes, config.RSI_PERIOD)
    short_ma = _compute_ma(closes, config.SHORT_MA)
    long_ma = _compute_ma(closes, config.LONG_MA)

    logger.debug("[%s] RSI=%.1f  단기MA=%.1f  장기MA=%.1f  현재가=%d",
                 symbol, rsi, short_ma, long_ma, current_price)

    position = state.positions.get(symbol)

    # ── 보유 중인 경우: 익절 / 손절 우선 확인 ──────────────────────────────────
    if position:
        pl_pct = (current_price - position.avg_price) / position.avg_price * 100
        if pl_pct >= config.TAKE_PROFIT_PCT:
            logger.info("[%s] 익절 신호 (수익률 %.2f%%)", symbol, pl_pct)
            return Signal.SELL
        if pl_pct <= -config.STOP_LOSS_PCT:
            logger.info("[%s] 손절 신호 (수익률 %.2f%%)", symbol, pl_pct)
            return Signal.SELL
        # 데드크로스 or RSI 과매수 → 매도
        if rsi >= config.RSI_SELL_THRESHOLD or short_ma < long_ma:
            logger.info("[%s] 매도 신호 (RSI=%.1f, 단기MA<장기MA=%s)",
                        symbol, rsi, short_ma < long_ma)
            return Signal.SELL
        return Signal.HOLD

    # ── 미보유인 경우: 매수 조건 확인 ─────────────────────────────────────────
    if rsi <= config.RSI_BUY_THRESHOLD and short_ma > long_ma:
        logger.info("[%s] 매수 신호 (RSI=%.1f, 골든크로스)", symbol, rsi)
        return Signal.BUY

    return Signal.HOLD


def calc_order_qty(cash: int, current_price: int) -> int:
    """
    ORDER_QTY > 0 이면 그대로 사용,
    ORDER_QTY == 0 이면 예수금의 MAX_POSITION_PCT% 내에서 최대 수량 계산.
    """
    if config.ORDER_QTY > 0:
        return config.ORDER_QTY
    if current_price <= 0:
        return 0
    max_amount = int(cash * config.MAX_POSITION_PCT / 100)
    return max(1, max_amount // current_price)
