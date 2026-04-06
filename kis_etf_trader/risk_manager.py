"""
포지션 및 리스크 관리 모듈
보유 종목의 매수 단가, 수량, 수익률을 추적하고
익절/손절 조건을 판단합니다.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .config import Config
from .logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class Position:
    ticker: str
    avg_price: float     # 평균 매수 단가
    qty: int             # 보유 수량
    entered_at: datetime = field(default_factory=datetime.now)


class RiskManager:
    """포지션 관리 및 익절·손절 판단."""

    def __init__(self) -> None:
        self._positions: dict[str, Position] = {}

    # ------------------------------------------------------------------
    # 포지션 관리
    # ------------------------------------------------------------------

    def open_position(self, ticker: str, price: float, qty: int) -> None:
        """신규 매수 포지션을 등록합니다."""
        if ticker in self._positions:
            # 추가 매수 시 평균 단가 재계산
            existing = self._positions[ticker]
            total_cost = existing.avg_price * existing.qty + price * qty
            new_qty = existing.qty + qty
            self._positions[ticker] = Position(
                ticker=ticker,
                avg_price=total_cost / new_qty,
                qty=new_qty,
                entered_at=existing.entered_at,
            )
        else:
            self._positions[ticker] = Position(ticker=ticker, avg_price=price, qty=qty)
        logger.info(
            "[포지션 오픈] %s | 단가: %,.0f원 | 수량: %d주",
            ticker, price, qty,
        )

    def close_position(self, ticker: str) -> Optional[Position]:
        """포지션을 제거하고 반환합니다."""
        return self._positions.pop(ticker, None)

    def has_position(self, ticker: str) -> bool:
        return ticker in self._positions

    def position_count(self) -> int:
        return len(self._positions)

    def get_position(self, ticker: str) -> Optional[Position]:
        return self._positions.get(ticker)

    def all_tickers(self) -> list[str]:
        return list(self._positions.keys())

    # ------------------------------------------------------------------
    # 익절·손절 판단
    # ------------------------------------------------------------------

    def should_take_profit(self, ticker: str, current_price: float) -> bool:
        """익절 조건: 수익률 >= Config.TAKE_PROFIT_PCT."""
        pos = self._positions.get(ticker)
        if pos is None:
            return False
        pnl_pct = (current_price - pos.avg_price) / pos.avg_price * 100
        if pnl_pct >= Config.TAKE_PROFIT_PCT:
            logger.info(
                "[익절 조건] %s | 수익률: %.2f%% (기준: +%.1f%%)",
                ticker, pnl_pct, Config.TAKE_PROFIT_PCT,
            )
            return True
        return False

    def should_stop_loss(self, ticker: str, current_price: float) -> bool:
        """손절 조건: 손실률 >= Config.STOP_LOSS_PCT."""
        pos = self._positions.get(ticker)
        if pos is None:
            return False
        pnl_pct = (current_price - pos.avg_price) / pos.avg_price * 100
        if pnl_pct <= -Config.STOP_LOSS_PCT:
            logger.info(
                "[손절 조건] %s | 수익률: %.2f%% (기준: -%.1f%%)",
                ticker, pnl_pct, Config.STOP_LOSS_PCT,
            )
            return True
        return False

    # ------------------------------------------------------------------
    # 매수 수량 산정
    # ------------------------------------------------------------------

    @staticmethod
    def calc_buy_qty(price: float) -> int:
        """설정된 1회 매수 금액으로 살 수 있는 수량을 반환합니다."""
        if price <= 0:
            return 0
        return max(1, int(Config.BUY_AMOUNT // price))

    # ------------------------------------------------------------------
    # 상태 출력
    # ------------------------------------------------------------------

    def log_positions(self, price_map: dict[str, float]) -> None:
        """현재 보유 포지션과 평가 손익을 로그로 출력합니다."""
        if not self._positions:
            logger.info("[포지션 없음]")
            return
        for ticker, pos in self._positions.items():
            cur = price_map.get(ticker, pos.avg_price)
            pnl_pct = (cur - pos.avg_price) / pos.avg_price * 100
            logger.info(
                "[보유] %s | 매수가: %,.0f | 현재가: %,.0f | 수익률: %+.2f%%",
                ticker, pos.avg_price, cur, pnl_pct,
            )
