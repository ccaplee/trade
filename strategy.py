"""
매매 전략 모듈
- MA5 / MA20 골든크로스 감지
- RSI 과매도 반등 감지
"""
import logging
from typing import Any

import config

logger = logging.getLogger(__name__)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# ── 지표 계산 ──────────────────────────────────────────────────────────────────

def calc_ma(prices: list[float], period: int) -> list[float]:
    """단순 이동평균(SMA)을 계산합니다."""
    if len(prices) < period:
        return []
    return [
        sum(prices[i : i + period]) / period
        for i in range(len(prices) - period + 1)
    ]


def calc_rsi(prices: list[float], period: int = 14) -> float:
    """
    마지막 종가 기준 RSI를 계산합니다.

    Wilder's Smoothed Moving Average 방식을 사용합니다.
    """
    if len(prices) < period + 1:
        return 50.0  # 데이터 부족 시 중립값 반환

    changes = [prices[i + 1] - prices[i] for i in range(len(prices) - 1)]
    gains = [max(c, 0.0) for c in changes]
    losses = [abs(min(c, 0.0)) for c in changes]

    # 초기 평균 (단순 평균)
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    # Wilder 스무딩
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


# ── 분봉 데이터 파싱 ───────────────────────────────────────────────────────────

def parse_candle_closes(candles: list[dict[str, Any]]) -> list[float]:
    """
    KIS API 분봉 응답에서 종가(stck_prpr / stck_clpr) 목록을 추출합니다.
    API는 최신 데이터가 앞에 오므로 시간 순으로 역정렬합니다.
    """
    prices: list[float] = []
    for c in reversed(candles):
        close = _safe_float(c.get("stck_clpr") or c.get("stck_prpr"))
        if close > 0:
            prices.append(close)
    return prices


# ── 매수 신호 ──────────────────────────────────────────────────────────────────

def should_buy(prices: list[float]) -> tuple[bool, str]:
    """
    매수 신호를 판단합니다.

    Parameters
    ----------
    prices : list[float]
        분봉 종가 리스트 (오래된 것 → 최신 순)

    Returns
    -------
    (signal: bool, reason: str)
    """
    min_len = max(config.MA_LONG + 1, config.RSI_PERIOD + 1)
    if len(prices) < min_len:
        return False, f"데이터 부족 ({len(prices)}/{min_len})"

    ma_short = calc_ma(prices, config.MA_SHORT)
    ma_long = calc_ma(prices, config.MA_LONG)

    if len(ma_short) < 2 or len(ma_long) < 2:
        return False, "이동평균 계산 불가"

    # MA 골든크로스: 이전 봉에서는 short <= long, 현재 봉에서는 short > long
    golden_cross = ma_short[-2] <= ma_long[-2] and ma_short[-1] > ma_long[-1]

    rsi = calc_rsi(prices, config.RSI_PERIOD)
    rsi_signal = rsi <= config.RSI_OVERSOLD

    if golden_cross and rsi_signal:
        reason = f"골든크로스 + RSI 과매도 반등 (RSI={rsi:.1f})"
        return True, reason
    if golden_cross:
        reason = f"골든크로스 (MA{config.MA_SHORT}={ma_short[-1]:.0f} > MA{config.MA_LONG}={ma_long[-1]:.0f})"
        return True, reason
    if rsi_signal:
        reason = f"RSI 과매도 반등 (RSI={rsi:.1f})"
        return True, reason

    return False, f"신호 없음 (RSI={rsi:.1f})"


# ── 매도 신호 ──────────────────────────────────────────────────────────────────

def should_sell(buy_price: float, current_price: float) -> tuple[bool, str]:
    """
    보유 포지션의 매도 신호를 판단합니다 (익절 / 손절).

    Parameters
    ----------
    buy_price : float
        매수 단가
    current_price : float
        현재가

    Returns
    -------
    (signal: bool, reason: str)
    """
    if buy_price <= 0:
        return False, "매수가 정보 없음"

    pnl_pct = (current_price - buy_price) / buy_price * 100

    if pnl_pct >= config.PROFIT_TAKE_PCT:
        return True, f"익절 (수익률 {pnl_pct:.2f}%)"
    if pnl_pct <= -config.STOP_LOSS_PCT:
        return True, f"손절 (수익률 {pnl_pct:.2f}%)"

    return False, f"보유 유지 (수익률 {pnl_pct:.2f}%)"
