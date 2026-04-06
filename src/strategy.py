"""
단타 매매 전략 모듈

전략: 모멘텀 + 변동성 돌파
- 매수 조건: 현재가가 시가 + (전일 고저폭 * k) 이상 상승 돌파 시
- 익절: 매수가 대비 +PROFIT_TARGET% 도달 시 시장가 매도
- 손절: 매수가 대비 -STOP_LOSS% 하락 시 시장가 매도
- 강제 청산: FORCE_CLOSE_TIME 이전에 모든 포지션 시장가 매도
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)

# 전략 파라미터
BREAKOUT_K = 0.5        # 변동성 돌파 계수 (0.3 ~ 0.7)
PROFIT_TARGET = 1.0     # 익절 목표 (%)
STOP_LOSS = 0.5         # 손절 기준 (%)
FORCE_CLOSE_HOUR = 15   # 강제 청산 시간 (시)
FORCE_CLOSE_MINUTE = 20 # 강제 청산 분
MAX_POSITION_RATIO = 0.2  # 종목당 최대 투자 비율 (총 자산 대비)


@dataclass
class Position:
    """보유 포지션 정보"""
    code: str
    name: str
    qty: int
    buy_price: float        # 매수 단가
    entry_time: datetime = field(default_factory=lambda: datetime.now())
    profit_target_price: float = 0.0
    stop_loss_price: float = 0.0

    def __post_init__(self):
        self.profit_target_price = self.buy_price * (1 + PROFIT_TARGET / 100)
        self.stop_loss_price = self.buy_price * (1 - STOP_LOSS / 100)

    @property
    def unrealized_pnl_pct(self) -> float:
        return 0.0  # 실시간 갱신은 Trader에서 처리


class Strategy:
    """단타 매매 전략"""

    @staticmethod
    def should_buy(
        current_price: int,
        open_price: int,
        prev_high: int,
        prev_low: int,
    ) -> bool:
        """
        변동성 돌파 매수 조건 판단.
        target = open_price + (prev_high - prev_low) * BREAKOUT_K
        현재가 >= target 이면 매수 신호
        """
        if open_price <= 0:
            return False
        prev_range = prev_high - prev_low
        if prev_range <= 0:
            return False
        target = open_price + prev_range * BREAKOUT_K
        return current_price >= target

    @staticmethod
    def should_take_profit(current_price: int, position: Position) -> bool:
        """익절 조건 판단"""
        return current_price >= position.profit_target_price

    @staticmethod
    def should_stop_loss(current_price: int, position: Position) -> bool:
        """손절 조건 판단"""
        return current_price <= position.stop_loss_price

    @staticmethod
    def should_force_close() -> bool:
        """강제 청산 시간 도달 여부"""
        now = datetime.now()
        return (now.hour > FORCE_CLOSE_HOUR) or (
            now.hour == FORCE_CLOSE_HOUR and now.minute >= FORCE_CLOSE_MINUTE
        )

    @staticmethod
    def calc_buy_qty(
        available_cash: int,
        current_price: int,
        total_asset: int,
    ) -> int:
        """
        매수 수량 계산.
        - 종목당 최대 MAX_POSITION_RATIO 비율 투자
        - 최소 1주
        """
        if current_price <= 0:
            return 0
        max_invest = int(total_asset * MAX_POSITION_RATIO)
        invest_amount = min(available_cash, max_invest)
        qty = invest_amount // current_price
        return max(qty, 0)

    @staticmethod
    def is_trading_time() -> bool:
        """현재 시간이 거래 가능한 시간대인지 확인합니다 (9:00 ~ 15:20)."""
        now = datetime.now()
        start = now.replace(hour=9, minute=0, second=0, microsecond=0)
        end = now.replace(
            hour=FORCE_CLOSE_HOUR,
            minute=FORCE_CLOSE_MINUTE,
            second=0,
            microsecond=0,
        )
        return start <= now <= end

    @staticmethod
    def is_market_open() -> bool:
        """현재 시간이 주식 시장 개장 시간인지 확인합니다 (9:00 ~ 15:30, 평일)."""
        now = datetime.now()
        if now.weekday() >= 5:  # 토/일
            return False
        start = now.replace(hour=9, minute=0, second=0, microsecond=0)
        end = now.replace(hour=15, minute=30, second=0, microsecond=0)
        return start <= now <= end
