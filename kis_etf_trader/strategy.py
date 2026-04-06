"""
매매 전략 모듈
분봉 데이터를 수집하여 매수·매도 신호를 생성합니다.

매수 신호:
  1. MA5(단기) 가 MA20(장기) 를 상향 돌파 (골든 크로스)
  2. RSI 가 과매도(30 이하)에서 반등

매도 신호:
  - 익절: 수익률 >= +1.5%
  - 손절: 수익률 <= -0.8%
"""

from typing import Any, Optional

from .api_client import KISClient
from .config import Config
from .indicators import compute_ma, compute_rsi, golden_cross
from .logger import setup_logger
from .risk_manager import RiskManager

logger = setup_logger(__name__)


def _parse_candles(raw: list[dict[str, Any]]) -> list[float]:
    """분봉 API 응답에서 종가(stck_prpr) 리스트를 추출합니다 (오래된 순).

    KIS 분봉 API는 최신 봉이 먼저 오므로 역순 정렬합니다.
    """
    prices: list[float] = []
    for candle in reversed(raw):
        try:
            prices.append(float(candle.get("stck_prpr", 0) or candle.get("stck_clpr", 0)))
        except (ValueError, TypeError):
            continue
    return prices


class TradingStrategy:
    """매수·매도 신호 생성 및 주문 실행."""

    def __init__(self, client: KISClient, risk_manager: RiskManager) -> None:
        self._client = client
        self._rm = risk_manager
        # RSI 과매도 진입 여부 추적: 직전 봉에서 RSI < 30 이었는지
        self._rsi_oversold_flag: dict[str, bool] = {}

    # ------------------------------------------------------------------
    # 신호 판단
    # ------------------------------------------------------------------

    def _get_prices(self, ticker: str) -> list[float]:
        """분봉 종가 리스트 반환. 최소 MA_LONG + 2 개 필요."""
        required = Config.MA_LONG + 2
        try:
            raw = self._client.get_minute_candles(ticker)
            prices = _parse_candles(raw)
        except Exception as exc:
            logger.warning("[%s] 분봉 조회 실패: %s", ticker, exc)
            return []

        if len(prices) < required:
            logger.debug("[%s] 분봉 데이터 부족: %d / %d", ticker, len(prices), required)
            return []
        return prices

    def check_buy_signal(self, ticker: str) -> bool:
        """매수 신호 여부를 반환합니다."""
        prices = self._get_prices(ticker)
        if not prices:
            return False

        ma_short_prev = compute_ma(prices[:-1], Config.MA_SHORT)
        ma_long_prev = compute_ma(prices[:-1], Config.MA_LONG)
        ma_short_curr = compute_ma(prices, Config.MA_SHORT)
        ma_long_curr = compute_ma(prices, Config.MA_LONG)

        is_golden = golden_cross(ma_short_prev, ma_long_prev, ma_short_curr, ma_long_curr)

        rsi = compute_rsi(prices, Config.RSI_PERIOD)
        prev_oversold = self._rsi_oversold_flag.get(ticker, False)
        is_rsi_rebound = prev_oversold and rsi is not None and rsi > Config.RSI_OVERSOLD

        # 다음 봉을 위해 RSI 과매도 상태 갱신
        self._rsi_oversold_flag[ticker] = rsi is not None and rsi <= Config.RSI_OVERSOLD

        signal = is_golden or is_rsi_rebound

        logger.debug(
            "[%s] MA5=%.1f MA20=%.1f RSI=%.1f | 골든크로스=%s RSI반등=%s",
            ticker,
            ma_short_curr or 0,
            ma_long_curr or 0,
            rsi or 0,
            is_golden,
            is_rsi_rebound,
        )
        return signal

    # ------------------------------------------------------------------
    # 매수 실행
    # ------------------------------------------------------------------

    def try_buy(self, ticker: str) -> bool:
        """매수 신호 확인 후 주문을 실행합니다.

        Returns:
            주문 실행 여부
        """
        if self._rm.has_position(ticker):
            return False
        if self._rm.position_count() >= Config.MAX_POSITIONS:
            logger.debug("최대 포지션 수 도달 (%d)", Config.MAX_POSITIONS)
            return False
        if not self.check_buy_signal(ticker):
            return False

        try:
            price_info = self._client.get_price(ticker)
            price = float(price_info.get("stck_prpr", 0))
        except Exception as exc:
            logger.warning("[%s] 현재가 조회 실패: %s", ticker, exc)
            return False

        if price <= 0:
            return False

        qty = self._rm.calc_buy_qty(price)
        if qty <= 0:
            return False

        try:
            self._client.buy_market_order(ticker, qty)
            self._rm.open_position(ticker, price, qty)
            return True
        except Exception as exc:
            logger.error("[%s] 매수 주문 실패: %s", ticker, exc)
            return False

    # ------------------------------------------------------------------
    # 매도 실행
    # ------------------------------------------------------------------

    def check_and_sell(self, ticker: str) -> bool:
        """익절·손절 조건을 확인하고 매도 주문을 실행합니다.

        Returns:
            주문 실행 여부
        """
        if not self._rm.has_position(ticker):
            return False

        try:
            price_info = self._client.get_price(ticker)
            current_price = float(price_info.get("stck_prpr", 0))
        except Exception as exc:
            logger.warning("[%s] 현재가 조회 실패 (매도 검토 생략): %s", ticker, exc)
            return False

        if current_price <= 0:
            return False

        take_profit = self._rm.should_take_profit(ticker, current_price)
        stop_loss = self._rm.should_stop_loss(ticker, current_price)

        if not (take_profit or stop_loss):
            return False

        pos = self._rm.get_position(ticker)
        if pos is None:
            return False

        reason = "익절" if take_profit else "손절"
        try:
            self._client.sell_market_order(ticker, pos.qty)
            self._rm.close_position(ticker)
            logger.info("[%s] %s 매도 완료 | 현재가: %,.0f원", ticker, reason, current_price)
            return True
        except Exception as exc:
            logger.error("[%s] 매도 주문 실패: %s", ticker, exc)
            return False
