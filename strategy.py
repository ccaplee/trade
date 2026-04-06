"""
단타 매매 전략 모듈
- RSI (Relative Strength Index)
- 이동평균선 골든/데드크로스
- 거래량 급증 필터
"""
import logging
import numpy as np

import config

logger = logging.getLogger(__name__)


def _closes(ohlcv: list[dict]) -> np.ndarray:
    """일봉 리스트에서 종가 배열 반환 (최신 → 가장 앞)"""
    return np.array([float(row["stck_clpr"]) for row in ohlcv], dtype=float)


def _volumes(ohlcv: list[dict]) -> np.ndarray:
    return np.array([float(row["acml_vol"]) for row in ohlcv], dtype=float)


def calc_rsi(closes: np.ndarray, period: int = 14) -> float:
    """
    단순 Wilder RSI 계산 (최근 period+1 개의 종가 사용)
    반환: 0 ~ 100 사이의 RSI 값
    """
    if len(closes) < period + 1:
        return 50.0  # 데이터 부족 시 중립값

    # 최신 데이터가 앞에 있으므로 역전
    c = closes[:period + 1][::-1]
    deltas = np.diff(c)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = gains.mean()
    avg_loss = losses.mean()
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def calc_ma(closes: np.ndarray, period: int) -> float:
    """단순 이동평균"""
    if len(closes) < period:
        return float(closes.mean())
    return float(closes[:period].mean())


def calc_volume_ratio(volumes: np.ndarray, avg_period: int = 5) -> float:
    """최근 거래량 / 과거 평균 거래량 비율"""
    if len(volumes) < avg_period + 1:
        return 1.0
    recent = volumes[0]
    avg = volumes[1: avg_period + 1].mean()
    if avg == 0:
        return 1.0
    return recent / avg


class SignalResult:
    """전략 신호 결과"""
    __slots__ = ("symbol", "signal", "rsi", "ma_short", "ma_long", "volume_ratio", "current_price")

    def __init__(
        self,
        symbol: str,
        signal: str,        # "BUY", "SELL", "HOLD"
        rsi: float,
        ma_short: float,
        ma_long: float,
        volume_ratio: float,
        current_price: float,
    ):
        self.symbol = symbol
        self.signal = signal
        self.rsi = rsi
        self.ma_short = ma_short
        self.ma_long = ma_long
        self.volume_ratio = volume_ratio
        self.current_price = current_price

    def __repr__(self) -> str:
        return (
            f"SignalResult(symbol={self.symbol}, signal={self.signal}, "
            f"rsi={self.rsi:.1f}, ma_short={self.ma_short:.0f}, ma_long={self.ma_long:.0f}, "
            f"vol_ratio={self.volume_ratio:.2f}, price={self.current_price:.0f})"
        )


def evaluate(symbol: str, ohlcv: list[dict], current_price: float) -> SignalResult:
    """
    매매 신호 평가

    매수 조건 (AND):
      1. RSI < RSI_BUY_THRESHOLD  (과매도)
      2. 단기 MA >= 장기 MA        (골든크로스 or 유지)
      3. 거래량 비율 >= MIN_VOLUME_RATIO (거래 급증)

    매도 조건 (OR):
      1. RSI > RSI_SELL_THRESHOLD (과매수)
      2. 단기 MA < 장기 MA         (데드크로스)
    """
    closes = _closes(ohlcv)
    volumes = _volumes(ohlcv)

    rsi = calc_rsi(closes, config.RSI_PERIOD)
    ma_s = calc_ma(closes, config.MA_SHORT)
    ma_l = calc_ma(closes, config.MA_LONG)
    vol_ratio = calc_volume_ratio(volumes)

    # 매수 신호
    buy_rsi = rsi < config.RSI_BUY_THRESHOLD
    buy_ma = ma_s >= ma_l
    buy_vol = vol_ratio >= config.MIN_VOLUME_RATIO
    buy_signal = buy_rsi and buy_ma and buy_vol

    # 매도 신호
    sell_rsi = rsi > config.RSI_SELL_THRESHOLD
    sell_ma = ma_s < ma_l
    sell_signal = sell_rsi or sell_ma

    if buy_signal:
        signal = "BUY"
    elif sell_signal:
        signal = "SELL"
    else:
        signal = "HOLD"

    result = SignalResult(
        symbol=symbol,
        signal=signal,
        rsi=rsi,
        ma_short=ma_s,
        ma_long=ma_l,
        volume_ratio=vol_ratio,
        current_price=current_price,
    )
    logger.debug("전략 평가: %s", result)
    return result
