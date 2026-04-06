"""
단타 매매 전략 모듈

RSI, 이동평균선, 볼린저 밴드를 활용한 ETF 단타 전략을 구현합니다.
매수/매도 신호를 생성하고 포지션을 관리합니다.
"""

from collections import deque
from dataclasses import dataclass, field
from typing import Optional
import numpy as np
from loguru import logger


@dataclass
class Position:
    """보유 포지션 정보"""
    stock_code: str
    quantity: int
    avg_price: float
    entry_time: str
    stop_loss_price: float = 0.0
    take_profit_price: float = 0.0

    def get_pnl_rate(self, current_price: float) -> float:
        if self.avg_price == 0 or current_price == 0:
            return 0.0
        return (current_price - self.avg_price) / self.avg_price * 100


@dataclass
class StrategyConfig:
    """전략 설정값"""
    rsi_period: int = 14
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    ma_short: int = 5
    ma_long: int = 20
    bb_period: int = 20
    bb_std: float = 2.0
    volume_ratio_min: float = 1.5
    stop_loss_pct: float = -1.5
    take_profit_pct: float = 1.0
    max_buy_amount: int = 500000
    max_positions: int = 3
    max_daily_loss_pct: float = -3.0


class PriceBuffer:
    """종목별 가격 데이터 버퍼 (실시간 업데이트)"""

    def __init__(self, maxlen: int = 200):
        self.closes: deque = deque(maxlen=maxlen)
        self.highs: deque = deque(maxlen=maxlen)
        self.lows: deque = deque(maxlen=maxlen)
        self.volumes: deque = deque(maxlen=maxlen)

    def update(self, close: float, high: float, low: float, volume: int):
        self.closes.append(close)
        self.highs.append(high)
        self.lows.append(low)
        self.volumes.append(volume)

    def load_history(self, daily_prices: list[dict]):
        """일별 시세 데이터로 초기화"""
        for item in reversed(daily_prices):
            self.closes.append(item["close"])
            self.highs.append(item["high"])
            self.lows.append(item["low"])
            self.volumes.append(item["volume"])

    def __len__(self):
        return len(self.closes)


class TechnicalIndicators:
    """기술적 지표 계산 클래스"""

    @staticmethod
    def rsi(prices: list[float], period: int = 14) -> Optional[float]:
        """RSI 계산"""
        if len(prices) < period + 1:
            return None
        deltas = np.diff(prices[-(period + 1):])
        gains = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)
        avg_gain = np.mean(gains[:period])
        avg_loss = np.mean(losses[:period])
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    @staticmethod
    def sma(prices: list[float], period: int) -> Optional[float]:
        """단순 이동평균 계산"""
        if len(prices) < period:
            return None
        return float(np.mean(prices[-period:]))

    @staticmethod
    def ema(prices: list[float], period: int) -> Optional[float]:
        """지수 이동평균 계산"""
        if len(prices) < period:
            return None
        arr = np.array(prices[-period * 3:] if len(prices) >= period * 3 else prices, dtype=float)
        k = 2.0 / (period + 1)
        ema_val = arr[0]
        for price in arr[1:]:
            ema_val = price * k + ema_val * (1 - k)
        return float(ema_val)

    @staticmethod
    def bollinger_bands(prices: list[float], period: int = 20, std_multiplier: float = 2.0) -> Optional[tuple]:
        """볼린저 밴드 계산 (upper, middle, lower)"""
        if len(prices) < period:
            return None
        recent = np.array(prices[-period:], dtype=float)
        middle = float(np.mean(recent))
        std = float(np.std(recent, ddof=1))
        return (middle + std_multiplier * std, middle, middle - std_multiplier * std)

    @staticmethod
    def volume_ratio(volumes: list[int], period: int = 20) -> Optional[float]:
        """현재 거래량 / 평균 거래량 비율"""
        if len(volumes) < period + 1:
            return None
        avg_vol = float(np.mean(list(volumes)[-(period + 1):-1]))
        if avg_vol == 0:
            return None
        return volumes[-1] / avg_vol


class ETFStrategy:
    """ETF 단타 전략

    진입 조건 (매수):
    1. RSI가 과매도(30) 이하에서 반등
    2. 단기 MA가 장기 MA 위 (골든크로스)
    3. 볼린저 밴드 하단 근처에서 반등
    4. 거래량 급증 확인

    청산 조건 (매도):
    1. RSI 과매수(70) 이상
    2. 손절가 도달 (기본 -1.5%)
    3. 익절가 도달 (기본 +1.0%)
    4. 장 마감 전 강제 청산
    """

    def __init__(self, config: StrategyConfig):
        self.config = config
        self.price_buffers: dict[str, PriceBuffer] = {}
        self.positions: dict[str, Position] = {}
        self.daily_pnl: float = 0.0
        self.initial_balance: float = 0.0

    def init_price_buffer(self, stock_code: str, daily_prices: list[dict]):
        """종목 가격 버퍼 초기화"""
        buf = PriceBuffer()
        buf.load_history(daily_prices)
        self.price_buffers[stock_code] = buf
        logger.debug("가격 버퍼 초기화 | {} ({} 개 데이터)", stock_code, len(buf))

    def update_price(self, stock_code: str, price_data: dict):
        """실시간 가격 업데이트"""
        if stock_code not in self.price_buffers:
            self.price_buffers[stock_code] = PriceBuffer()
        buf = self.price_buffers[stock_code]
        buf.update(
            close=price_data["current_price"],
            high=price_data.get("high_price", price_data["current_price"]),
            low=price_data.get("low_price", price_data["current_price"]),
            volume=price_data.get("volume", 0),
        )

    def check_buy_signal(self, stock_code: str, current_price: int) -> bool:
        """매수 신호 확인"""
        if stock_code in self.positions:
            return False
        if len(self.positions) >= self.config.max_positions:
            return False
        if self.daily_pnl <= self.config.max_daily_loss_pct and self.initial_balance > 0:
            logger.warning("일일 손실 한도 초과 - 신규 매수 중단")
            return False

        buf = self.price_buffers.get(stock_code)
        if buf is None or len(buf) < self.config.ma_long:
            return False

        closes = list(buf.closes)
        volumes = list(buf.volumes)

        rsi = TechnicalIndicators.rsi(closes, self.config.rsi_period)
        ma_short = TechnicalIndicators.sma(closes, self.config.ma_short)
        ma_long = TechnicalIndicators.sma(closes, self.config.ma_long)
        bb = TechnicalIndicators.bollinger_bands(closes, self.config.bb_period, self.config.bb_std)
        vol_ratio = TechnicalIndicators.volume_ratio(volumes)

        if any(v is None for v in [rsi, ma_short, ma_long, bb, vol_ratio]):
            return False

        bb_upper, bb_middle, bb_lower = bb

        # 매수 조건 평가
        rsi_signal = rsi <= self.config.rsi_oversold + 5  # RSI 과매도 또는 회복 초기
        ma_signal = ma_short >= ma_long  # 단기 MA >= 장기 MA (상승 추세)
        bb_signal = current_price <= bb_middle  # 볼린저 중간선 이하 (저가 매수)
        volume_signal = vol_ratio >= self.config.volume_ratio_min  # 거래량 급증

        # 조건 중 2개 이상 충족 시 매수
        signals = [rsi_signal, ma_signal, bb_signal, volume_signal]
        met = sum(signals)

        if met >= 2:
            logger.info(
                "매수 신호 | {} 현재가={} RSI={:.1f} MA단={:.0f}/장={:.0f} BB중={:.0f} 거래량비율={:.1f} (조건충족: {}/4)",
                stock_code, current_price, rsi, ma_short, ma_long, bb_middle, vol_ratio, met
            )
            return True
        return False

    def check_sell_signal(self, stock_code: str, current_price: int) -> tuple[bool, str]:
        """매도 신호 확인

        Returns:
            (매도 여부, 매도 사유)
        """
        position = self.positions.get(stock_code)
        if position is None:
            return False, ""

        pnl_rate = (current_price - position.avg_price) / position.avg_price * 100

        # 손절
        if pnl_rate <= self.config.stop_loss_pct:
            return True, f"손절 (수익률: {pnl_rate:.2f}%)"

        # 익절
        if pnl_rate >= self.config.take_profit_pct:
            return True, f"익절 (수익률: {pnl_rate:.2f}%)"

        # RSI 과매수
        buf = self.price_buffers.get(stock_code)
        if buf and len(buf) >= self.config.rsi_period + 1:
            rsi = TechnicalIndicators.rsi(list(buf.closes), self.config.rsi_period)
            if rsi and rsi >= self.config.rsi_overbought:
                return True, f"RSI 과매수 ({rsi:.1f})"

        return False, ""

    def open_position(self, stock_code: str, quantity: int, price: int, timestamp: str):
        """포지션 진입"""
        stop_loss = price * (1 + self.config.stop_loss_pct / 100)
        take_profit = price * (1 + self.config.take_profit_pct / 100)
        self.positions[stock_code] = Position(
            stock_code=stock_code,
            quantity=quantity,
            avg_price=float(price),
            entry_time=timestamp,
            stop_loss_price=stop_loss,
            take_profit_price=take_profit,
        )
        logger.info(
            "포지션 진입 | {} {}주 @{} (손절={:.0f} 익절={:.0f})",
            stock_code, quantity, price, stop_loss, take_profit
        )

    def close_position(self, stock_code: str, sell_price: int) -> float:
        """포지션 청산 및 손익 반환"""
        position = self.positions.pop(stock_code, None)
        if position is None:
            return 0.0
        pnl = (sell_price - position.avg_price) * position.quantity
        pnl_rate = (sell_price - position.avg_price) / position.avg_price * 100
        self.daily_pnl += pnl_rate
        logger.info(
            "포지션 청산 | {} {}주 매도가={} 수익={:,.0f}원 ({:.2f}%)",
            stock_code, position.quantity, sell_price, pnl, pnl_rate
        )
        return pnl

    def calculate_buy_quantity(self, stock_code: str, current_price: int, available_cash: int) -> int:
        """매수 수량 계산"""
        max_amount = min(self.config.max_buy_amount, available_cash)
        if max_amount < current_price:
            return 0
        quantity = max_amount // current_price
        return max(1, quantity)

    def get_all_positions(self) -> list[Position]:
        return list(self.positions.values())

    def has_position(self, stock_code: str) -> bool:
        return stock_code in self.positions

    def get_position(self, stock_code: str) -> Optional[Position]:
        return self.positions.get(stock_code)
