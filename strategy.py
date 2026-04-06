"""
Trading strategy module.

Provides:
- select_top_etfs()  : rank ETF universe by volume × volatility
- compute_indicators(): calculate MA5, MA20, RSI from candle data
- should_buy()        : golden-cross or RSI-bounce signal
- should_sell()       : take-profit / stop-loss check
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

import config
import kis_api

logger = logging.getLogger(__name__)


# ── ETF selection ──────────────────────────────────────────────────────────────

def select_top_etfs(universe: list[str] = config.ETF_UNIVERSE, top_n: int = config.TOP_N_ETF) -> list[str]:
    """
    Screen *universe* and return the top *top_n* tickers ranked by
    volume × volatility (a simple proxy for intraday trading opportunity).
    """
    scores: list[tuple[float, str]] = []

    for ticker in universe:
        try:
            volume, volatility = kis_api.get_volume_and_volatility(ticker)
            score = volume * volatility
            scores.append((score, ticker))
            logger.debug("Screened %s: vol=%d vola=%.2f%% score=%.0f", ticker, volume, volatility, score)
        except Exception as exc:
            logger.warning("Could not screen %s: %s", ticker, exc)

    scores.sort(reverse=True)
    selected = [ticker for _, ticker in scores[:top_n]]
    logger.info("Top %d ETFs selected: %s", top_n, selected)
    return selected


# ── Technical indicators ───────────────────────────────────────────────────────

def compute_indicators(candles: list[dict]) -> Optional[pd.DataFrame]:
    """
    Build a DataFrame with columns: open, high, low, close, volume,
    ma_short, ma_long, rsi.

    Returns None if there are insufficient candles.
    """
    if len(candles) < config.MA_LONG + 1:
        return None

    df = pd.DataFrame(candles)
    df["close"] = df["close"].astype(float)

    df["ma_short"] = df["close"].rolling(config.MA_SHORT).mean()
    df["ma_long"] = df["close"].rolling(config.MA_LONG).mean()
    df["rsi"] = _rsi(df["close"], config.RSI_PERIOD)

    return df


def _rsi(series: pd.Series, period: int) -> pd.Series:
    """Wilder-smoothed RSI."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


# ── Buy / Sell signals ─────────────────────────────────────────────────────────

def should_buy(df: pd.DataFrame) -> tuple[bool, str]:
    """
    Return (True, reason) when a buy signal fires, otherwise (False, "").

    Conditions (either is sufficient):
      1. Golden cross: MA_SHORT crosses above MA_LONG on the latest closed bar.
      2. RSI bounce: RSI was ≤ RSI_OVERSOLD on the previous bar and has risen.
    """
    if df is None or len(df) < 2:
        return False, ""

    prev = df.iloc[-2]
    curr = df.iloc[-1]

    # Guard against NaN
    if any(pd.isna([prev["ma_short"], prev["ma_long"], curr["ma_short"], curr["ma_long"]])):
        return False, ""

    # 1. Golden cross
    if prev["ma_short"] <= prev["ma_long"] and curr["ma_short"] > curr["ma_long"]:
        return True, "golden_cross"

    # 2. RSI bounce from oversold
    if prev["rsi"] <= config.RSI_OVERSOLD and curr["rsi"] > prev["rsi"]:
        return True, "rsi_bounce"

    return False, ""


def should_sell(current_price: float, buy_price: float) -> tuple[bool, str]:
    """
    Return (True, reason) when a sell signal fires, otherwise (False, "").

    Conditions:
      1. Take-profit: current return ≥ TAKE_PROFIT_PCT
      2. Stop-loss:   current return ≤ STOP_LOSS_PCT (negative)
    """
    pnl = (current_price - buy_price) / buy_price

    if pnl >= config.TAKE_PROFIT_PCT:
        return True, f"take_profit ({pnl*100:.2f}%)"

    if pnl <= config.STOP_LOSS_PCT:
        return True, f"stop_loss ({pnl*100:.2f}%)"

    return False, ""
