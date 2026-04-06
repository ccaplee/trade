"""
기술적 지표 계산 모듈
이동평균(MA), RSI를 계산합니다.
"""

from typing import Optional

import numpy as np
import pandas as pd


def compute_ma(prices: list[float], period: int) -> Optional[float]:
    """단순 이동평균(SMA)을 계산합니다.

    Args:
        prices: 종가 리스트 (오래된 순 → 최신 순)
        period: 이동평균 기간

    Returns:
        최신 MA 값. 데이터가 부족하면 None.
    """
    if len(prices) < period:
        return None
    return float(np.mean(prices[-period:]))


def compute_rsi(prices: list[float], period: int = 14) -> Optional[float]:
    """Wilder RSI를 계산합니다.

    Args:
        prices: 종가 리스트 (오래된 순 → 최신 순), 최소 period+1개 필요
        period: RSI 기간 (기본 14)

    Returns:
        최신 RSI 값 (0~100). 데이터가 부족하면 None.
    """
    if len(prices) < period + 1:
        return None

    series = pd.Series(prices, dtype=float)
    delta = series.diff().dropna()

    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)

    # Wilder 평활 이동평균
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    return float(rsi.iloc[-1])


def golden_cross(ma_short_prev: Optional[float],
                 ma_long_prev: Optional[float],
                 ma_short_curr: Optional[float],
                 ma_long_curr: Optional[float]) -> bool:
    """단기 MA가 장기 MA를 상향 돌파(골든 크로스)했는지 확인합니다.

    Returns:
        이전 봉에서 단기 < 장기이고, 현재 봉에서 단기 >= 장기이면 True.
    """
    if any(v is None for v in [ma_short_prev, ma_long_prev, ma_short_curr, ma_long_curr]):
        return False
    return (ma_short_prev < ma_long_prev) and (ma_short_curr >= ma_long_curr)  # type: ignore[operator]
