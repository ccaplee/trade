"""
포지션 관리 모듈
매수 진입 후 수익률 / 손절 기준 도달 여부를 추적합니다.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime

import config

logger = logging.getLogger(__name__)


@dataclass
class Position:
    symbol: str
    avg_price: float          # 평균 매수가
    quantity: int             # 보유 수량
    entered_at: datetime = field(default_factory=datetime.now)

    @property
    def cost(self) -> float:
        return self.avg_price * self.quantity

    def pnl_rate(self, current_price: float) -> float:
        """수익률(%)"""
        return (current_price - self.avg_price) / self.avg_price * 100.0

    def should_take_profit(self, current_price: float) -> bool:
        return self.pnl_rate(current_price) >= config.TAKE_PROFIT_RATE

    def should_stop_loss(self, current_price: float) -> bool:
        return self.pnl_rate(current_price) <= -config.STOP_LOSS_RATE

    def __repr__(self) -> str:
        return (
            f"Position({self.symbol}, qty={self.quantity}, "
            f"avg={self.avg_price:.0f}, entered={self.entered_at:%H:%M:%S})"
        )


class PositionManager:
    """보유 포지션 딕셔너리 관리"""

    def __init__(self):
        self._positions: dict[str, Position] = {}

    def add(self, symbol: str, price: float, quantity: int) -> None:
        if symbol in self._positions:
            # 평균단가 재계산
            pos = self._positions[symbol]
            total_qty = pos.quantity + quantity
            avg = (pos.avg_price * pos.quantity + price * quantity) / total_qty
            pos.avg_price = avg
            pos.quantity = total_qty
        else:
            self._positions[symbol] = Position(symbol, price, quantity)
        logger.info("[포지션 추가] %s", self._positions[symbol])

    def remove(self, symbol: str) -> None:
        if symbol in self._positions:
            logger.info("[포지션 청산] %s", self._positions[symbol])
            del self._positions[symbol]

    def get(self, symbol: str) -> Position | None:
        return self._positions.get(symbol)

    def has(self, symbol: str) -> bool:
        return symbol in self._positions

    def count(self) -> int:
        return len(self._positions)

    def all(self) -> list[Position]:
        return list(self._positions.values())

    def check_exit(self, symbol: str, current_price: float) -> str | None:
        """
        청산 조건 확인
        반환: "TAKE_PROFIT" | "STOP_LOSS" | "STRATEGY_SELL" | None
        """
        pos = self.get(symbol)
        if pos is None:
            return None
        if pos.should_take_profit(current_price):
            rate = pos.pnl_rate(current_price)
            logger.info(
                "[익절] %s 현재가=%d 수익률=%.2f%%", symbol, current_price, rate
            )
            return "TAKE_PROFIT"
        if pos.should_stop_loss(current_price):
            rate = pos.pnl_rate(current_price)
            logger.info(
                "[손절] %s 현재가=%d 수익률=%.2f%%", symbol, current_price, rate
            )
            return "STOP_LOSS"
        return None
