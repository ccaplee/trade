# trader.py - 메인 트레이딩 루프

import logging
import time
from datetime import datetime

import config
from kis_api import KISApi
from strategy import (
    Position,
    Signal,
    StrategyState,
    calc_order_qty,
    generate_signal,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class Trader:
    """KIS ETF 단타 자동매매 트레이더."""

    def __init__(self):
        self.api = KISApi()
        # 보유 포지션: {ticker: Position}
        self.positions: dict[str, Position] = {}
        # 종목별 전략 상태: {ticker: StrategyState}
        self.states: dict[str, StrategyState] = {}
        # 오늘 선별된 ETF 목록
        self.target_etfs: list[str] = []

    # ── 시장 시간 유틸 ────────────────────────────────────────────────────────────

    @staticmethod
    def _now_str() -> str:
        return datetime.now().strftime("%H:%M")

    @staticmethod
    def _is_market_open() -> bool:
        now = datetime.now().strftime("%H:%M")
        return config.MARKET_OPEN <= now < config.MARKET_CLOSE

    # ── ETF 선별 ──────────────────────────────────────────────────────────────────

    def _refresh_target_etfs(self):
        """장 시작 후 거래량·변동성 기준 상위 ETF를 선별합니다."""
        logger.info("ETF 선별 시작 (후보 %d 개)", len(config.ETF_UNIVERSE))
        self.target_etfs = self.api.get_top_volume_etfs(top_n=config.TOP_ETF_COUNT)
        # 신규 종목에 대한 전략 상태 초기화
        for ticker in self.target_etfs:
            if ticker not in self.states:
                self.states[ticker] = StrategyState()
        logger.info("선별 완료: %s", self.target_etfs)

    # ── 포지션 동기화 ─────────────────────────────────────────────────────────────

    def _sync_positions(self):
        """API에서 실제 잔고를 조회하여 포지션 딕셔너리를 동기화합니다."""
        try:
            balance = self.api.get_balance()
            api_positions = balance["positions"]

            # API에 없는 포지션은 제거
            for ticker in list(self.positions.keys()):
                if ticker not in api_positions:
                    logger.info("[%s] 포지션 제거 (잔고 없음)", ticker)
                    del self.positions[ticker]

            # API 잔고 기반으로 포지션 업데이트
            for ticker, info in api_positions.items():
                if ticker in self.positions:
                    self.positions[ticker].qty = info["qty"]
                    self.positions[ticker].avg_price = info["avg_price"]
                else:
                    self.positions[ticker] = Position(
                        ticker=ticker,
                        qty=info["qty"],
                        avg_price=info["avg_price"],
                    )
        except Exception as exc:
            logger.warning("포지션 동기화 실패: %s", exc)

    # ── 매매 실행 ────────────────────────────────────────────────────────────────

    def _handle_buy(self, ticker: str, cash: float, current_price: float):
        """매수 조건 충족 시 주문을 실행합니다."""
        if len(self.positions) >= config.MAX_POSITIONS:
            logger.info("[%s] 매수 건너뜀: 최대 보유 종목 수(%d) 초과", ticker, config.MAX_POSITIONS)
            return

        if ticker in self.positions:
            return  # 이미 보유 중

        qty = calc_order_qty(cash, current_price)
        if qty <= 0:
            logger.info("[%s] 매수 건너뜀: 주문 가능 수량 없음 (현재가 %.0f, 예수금 %.0f)", ticker, current_price, cash)
            return

        try:
            self.api.buy(ticker, qty)
            self.positions[ticker] = Position(
                ticker=ticker,
                qty=qty,
                avg_price=current_price,
                entry_time=self._now_str(),
            )
            logger.info("[%s] 매수 완료: %d주 @ %.0f원", ticker, qty, current_price)
        except Exception as exc:
            logger.error("[%s] 매수 오류: %s", ticker, exc)

    def _handle_sell(self, ticker: str, signal: Signal):
        """매도 조건 충족 시 주문을 실행합니다."""
        position = self.positions.get(ticker)
        if position is None:
            return

        reason = "익절" if signal == Signal.SELL_PROFIT else "손절"
        try:
            self.api.sell(ticker, position.qty)
            del self.positions[ticker]
            logger.info("[%s] %s 완료: %d주", ticker, reason, position.qty)
        except Exception as exc:
            logger.error("[%s] 매도 오류: %s", ticker, exc)

    # ── 메인 루프 ─────────────────────────────────────────────────────────────────

    def run(self):
        """트레이딩 루프를 실행합니다."""
        logger.info("=== KIS ETF 자동매매 시작 (모의: %s) ===", config.IS_PAPER_TRADING)

        etf_refresh_done = False  # 당일 ETF 선별 완료 여부

        while True:
            try:
                if not self._is_market_open():
                    now = self._now_str()
                    # 장 마감 후 보유 잔고 정리
                    if now >= config.MARKET_CLOSE and self.positions:
                        logger.info("장 마감 → 보유 포지션 전량 매도")
                        self._sync_positions()
                        for ticker in list(self.positions.keys()):
                            self._handle_sell(ticker, Signal.SELL_LOSS)
                        etf_refresh_done = False  # 다음 날 재선별
                    logger.debug("장외 시간 (%s). 대기 중...", now)
                    time.sleep(config.LOOP_INTERVAL_SEC)
                    continue

                # 장 시작 직후 1회 ETF 선별
                if not etf_refresh_done:
                    self._refresh_target_etfs()
                    etf_refresh_done = True

                # 잔고 동기화
                self._sync_positions()
                balance = self.api.get_balance()
                cash = balance["cash"]

                # 각 ETF 전략 평가
                for ticker in self.target_etfs:
                    try:
                        candles = self.api.get_minute_candles(ticker, interval=5)
                        price_info = self.api.get_current_price(ticker)
                        current_price = price_info["current_price"]
                        position = self.positions.get(ticker)
                        state = self.states.setdefault(ticker, StrategyState())

                        signal = generate_signal(ticker, candles, position, state)

                        if signal == Signal.BUY:
                            self._handle_buy(ticker, cash, current_price)
                        elif signal in (Signal.SELL_PROFIT, Signal.SELL_LOSS):
                            self._handle_sell(ticker, signal)

                    except Exception as exc:
                        logger.warning("[%s] 처리 중 오류: %s", ticker, exc)

                logger.info(
                    "루프 완료 | 보유: %s | 예수금: %.0f원",
                    list(self.positions.keys()),
                    cash,
                )

            except KeyboardInterrupt:
                logger.info("사용자 인터럽트 — 프로그램 종료")
                break
            except Exception as exc:
                logger.error("예상치 못한 오류: %s", exc, exc_info=True)

            time.sleep(config.LOOP_INTERVAL_SEC)


if __name__ == "__main__":
    Trader().run()
