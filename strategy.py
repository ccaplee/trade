"""
매매 전략 모듈

매수 신호:
  1. 5분봉 MA5 가 MA20 을 상향 돌파 (골든크로스)
  2. RSI(14) 가 30 이하에서 반등 (과매도 반등)

매도 신호:
  - 매수 후 현재가가 평균 매수가 대비 +1.5% 이상 (익절)
  - 매수 후 현재가가 평균 매수가 대비 -1.0% 이하 (손절)
"""

from __future__ import annotations

import logging
from typing import Any

import config

logger = logging.getLogger(__name__)


# ── 보조 지표 계산 ────────────────────────────────────────────────────────────

def _sma(prices: list[float], period: int) -> float | None:
    """단순 이동평균. 데이터 부족 시 None 반환."""
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period


def _rsi(prices: list[float], period: int = 14) -> float | None:
    """Wilder RSI. 데이터 부족 시 None 반환."""
    if len(prices) < period + 1:
        return None

    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    seed_deltas = deltas[:period]

    # 초기 평균 (단순평균) – seed 구간의 실제 등락만 사용
    avg_gain = sum(d for d in seed_deltas if d > 0) / period
    avg_loss = sum(-d for d in seed_deltas if d < 0) / period

    # Wilder 평활
    for delta in deltas[period:]:
        gain = delta if delta > 0 else 0.0
        loss = -delta if delta < 0 else 0.0
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _parse_candles(raw: list[dict[str, Any]]) -> list[float]:
    """KIS 분봉 응답(최신→과거)에서 종가 리스트(과거→최신)를 추출합니다."""
    closes: list[float] = []
    for c in reversed(raw):
        try:
            closes.append(float(c.get("stck_clpr", 0)))
        except (ValueError, TypeError):
            pass
    return closes


# ── 신호 판단 ─────────────────────────────────────────────────────────────────

def check_buy_signal(candles: list[dict[str, Any]]) -> bool:
    """매수 신호 여부를 반환합니다.

    조건 (OR):
      A. 직전 봉: MA5 < MA20, 현재 봉: MA5 > MA20  (골든크로스)
      B. 직전 RSI ≤ RSI_OVERSOLD 이고 현재 RSI > RSI_OVERSOLD  (RSI 반등)
    """
    closes = _parse_candles(candles)
    if len(closes) < config.MA_LONG + 1:
        return False

    # 현재/이전 MA
    ma5_now = _sma(closes, config.MA_SHORT)
    ma20_now = _sma(closes, config.MA_LONG)
    ma5_prev = _sma(closes[:-1], config.MA_SHORT)
    ma20_prev = _sma(closes[:-1], config.MA_LONG)

    golden_cross = (
        ma5_prev is not None
        and ma20_prev is not None
        and ma5_now is not None
        and ma20_now is not None
        and ma5_prev <= ma20_prev
        and ma5_now > ma20_now
    )

    # RSI 반등
    rsi_now = _rsi(closes, config.RSI_PERIOD)
    rsi_prev = _rsi(closes[:-1], config.RSI_PERIOD)
    rsi_bounce = (
        rsi_prev is not None
        and rsi_now is not None
        and rsi_prev <= config.RSI_OVERSOLD
        and rsi_now > config.RSI_OVERSOLD
    )

    if golden_cross:
        logger.debug("매수 신호: 골든크로스 (MA5=%.2f, MA20=%.2f)", ma5_now, ma20_now)
    if rsi_bounce:
        logger.debug("매수 신호: RSI 반등 (RSI=%.2f)", rsi_now)

    return golden_cross or rsi_bounce


def check_sell_signal(avg_buy_price: float, current_price: float) -> tuple[bool, str]:
    """매도 신호 여부와 사유를 반환합니다.

    Returns:
        (should_sell, reason)
    """
    if avg_buy_price <= 0:
        return False, ""

    pnl_pct = (current_price - avg_buy_price) / avg_buy_price * 100

    if pnl_pct >= config.TAKE_PROFIT_PCT:
        logger.debug("매도 신호: 익절 (수익률=%.2f%%)", pnl_pct)
        return True, f"익절 ({pnl_pct:.2f}%)"

    if pnl_pct <= -config.STOP_LOSS_PCT:
        logger.debug("매도 신호: 손절 (수익률=%.2f%%)", pnl_pct)
        return True, f"손절 ({pnl_pct:.2f}%)"

    return False, ""
