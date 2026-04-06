"""
strategy.py
───────────
ETF 단타 매매 전략 모듈.

알고리즘
1. 모멘텀 전략  : 최근 N봉 수익률이 threshold 이상이면 매수 진입
2. 평균 회귀 전략: RSI 가 oversold 이하이면 매수, overbought 이상이면 매도
3. 이익실현 / 손절: 보유 중 수익률 >= take_profit → 매도
                    보유 중 수익률 <= -stop_loss  → 손절
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Deque

import numpy as np

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# 데이터 클래스
# ──────────────────────────────────────────────────────────────

@dataclass
class Signal:
    symbol: str
    action: str          # "BUY" | "SELL" | "HOLD"
    reason: str = ""
    price: float = 0.0


@dataclass
class PriceBar:
    """단일 가격 봉 (틱/분봉 공용)."""
    close: float
    volume: int = 0


# ──────────────────────────────────────────────────────────────
# 보조 지표
# ──────────────────────────────────────────────────────────────

def _rsi(closes: list[float], period: int) -> float:
    """RSI 계산 (Wilder 방식)."""
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))
    # 초기 평균
    avg_gain = float(np.mean(gains[:period]))
    avg_loss = float(np.mean(losses[:period]))
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1 + rs))


def _momentum_return(closes: list[float], period: int) -> float:
    """period 봉 전 대비 현재 수익률."""
    if len(closes) <= period:
        return 0.0
    return (closes[-1] - closes[-period - 1]) / closes[-period - 1]


# ──────────────────────────────────────────────────────────────
# 종목별 가격 히스토리 관리
# ──────────────────────────────────────────────────────────────

class SymbolHistory:
    """종목 하나의 가격 히스토리를 보관."""

    def __init__(self, max_bars: int = 60) -> None:
        self._bars: Deque[PriceBar] = deque(maxlen=max_bars)

    def push(self, price: float, volume: int = 0) -> None:
        self._bars.append(PriceBar(close=price, volume=volume))

    @property
    def closes(self) -> list[float]:
        return [b.close for b in self._bars]

    def __len__(self) -> int:
        return len(self._bars)


# ──────────────────────────────────────────────────────────────
# 전략 엔진
# ──────────────────────────────────────────────────────────────

@dataclass
class StrategyConfig:
    momentum_period: int = 5
    momentum_threshold: float = 0.003
    rsi_period: int = 14
    rsi_oversold: float = 35.0
    rsi_overbought: float = 65.0
    take_profit: float = 0.005
    stop_loss: float = 0.003
    max_positions: int = 3
    position_size: float = 0.2
    daily_loss_limit: float = 0.02
    max_trade_amount: int = 1_000_000
    price_history_bars: int = 60


class ScalpingStrategy:
    """모멘텀 + RSI 평균회귀 복합 단타 전략."""

    def __init__(self, cfg: StrategyConfig) -> None:
        self.cfg = cfg
        self._histories: dict[str, SymbolHistory] = {}

    # ── 가격 업데이트 ──────────────────────────────────────────

    def update_price(self, symbol: str, price: float, volume: int = 0) -> None:
        if symbol not in self._histories:
            self._histories[symbol] = SymbolHistory(max_bars=self.cfg.price_history_bars)
        self._histories[symbol].push(price, volume)

    # ── 매수 신호 생성 ─────────────────────────────────────────

    def entry_signal(self, symbol: str, current_positions: int) -> Signal:
        """
        매수 진입 신호 판단.
        - 이미 보유 중이거나 max_positions 초과 시 HOLD
        - 모멘텀 or RSI 과매도 조건 중 하나 충족 시 BUY
        """
        if current_positions >= self.cfg.max_positions:
            return Signal(symbol=symbol, action="HOLD", reason="포지션 한도 도달")

        hist = self._histories.get(symbol)
        if hist is None or len(hist) < self.cfg.rsi_period + 2:
            return Signal(symbol=symbol, action="HOLD", reason="데이터 부족")

        closes = hist.closes
        rsi = _rsi(closes, self.cfg.rsi_period)
        mom = _momentum_return(closes, self.cfg.momentum_period)

        if rsi <= self.cfg.rsi_oversold:
            return Signal(
                symbol=symbol, action="BUY",
                reason=f"RSI 과매도 ({rsi:.1f})",
                price=closes[-1],
            )
        if mom >= self.cfg.momentum_threshold:
            return Signal(
                symbol=symbol, action="BUY",
                reason=f"모멘텀 상승 ({mom * 100:.2f}%)",
                price=closes[-1],
            )
        return Signal(symbol=symbol, action="HOLD", reason="조건 미충족")

    # ── 청산 신호 생성 ─────────────────────────────────────────

    def exit_signal(self, symbol: str, entry_price: float, current_price: float) -> Signal:
        """
        보유 포지션 청산 신호 판단.
        - 수익률 >= take_profit → 이익실현 매도
        - 수익률 <= -stop_loss  → 손절 매도
        - RSI overbought         → 과매수 청산
        """
        if entry_price <= 0:
            return Signal(symbol=symbol, action="HOLD")

        pnl = (current_price - entry_price) / entry_price

        if pnl >= self.cfg.take_profit:
            return Signal(
                symbol=symbol, action="SELL",
                reason=f"이익실현 ({pnl * 100:.2f}%)",
                price=current_price,
            )
        if pnl <= -self.cfg.stop_loss:
            return Signal(
                symbol=symbol, action="SELL",
                reason=f"손절 ({pnl * 100:.2f}%)",
                price=current_price,
            )

        hist = self._histories.get(symbol)
        if hist and len(hist) >= self.cfg.rsi_period + 2:
            rsi = _rsi(hist.closes, self.cfg.rsi_period)
            if rsi >= self.cfg.rsi_overbought:
                return Signal(
                    symbol=symbol, action="SELL",
                    reason=f"RSI 과매수 ({rsi:.1f})",
                    price=current_price,
                )

        return Signal(symbol=symbol, action="HOLD")

    # ── 매매 수량 계산 ─────────────────────────────────────────

    def calc_qty(self, available_cash: int, price: float) -> int:
        """매수 수량 계산 (포지션 비중 + 최대 금액 제한)."""
        if price <= 0:
            return 0
        budget = min(
            int(available_cash * self.cfg.position_size),
            self.cfg.max_trade_amount,
        )
        qty = int(budget // price)
        return max(qty, 0)
