"""
메인 자동매매 봇
- 주기적으로 ETF 시세/일봉 조회
- 전략 신호에 따라 매수/매도 실행
- 보유 포지션 익절/손절 관리
"""
import logging
import time
from datetime import datetime

import pytz

import config
from kis_api import KISClient
from strategy import evaluate
from position import PositionManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("trader.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

KST = pytz.timezone("Asia/Seoul")


def is_market_open() -> bool:
    """현재 시각이 장 운영 시간 내인지 확인"""
    now = datetime.now(KST)
    if now.weekday() >= 5:  # 토/일
        return False
    t = now.strftime("%H:%M")
    return config.MARKET_OPEN_TIME <= t <= config.MARKET_CLOSE_TIME


def is_new_buy_allowed() -> bool:
    """신규 매수 가능 여부 (마감 10분 전 이후 신규 매수 금지)"""
    now = datetime.now(KST)
    t = now.strftime("%H:%M")
    return config.MARKET_OPEN_TIME <= t < config.MARKET_CLOSE_TIME


def calc_buy_quantity(price: float, budget: float) -> int:
    """주어진 예산으로 매수 가능한 최대 수량"""
    if price <= 0:
        return 0
    return max(0, int(budget // price))


class Trader:
    def __init__(self):
        self.client = KISClient()
        self.positions = PositionManager()

    # ── 핵심 루프 ──────────────────────────────────────────────────────────────

    def run(self) -> None:
        logger.info("=" * 60)
        logger.info("KIS ETF 단타 자동매매 봇 시작")
        logger.info("환경: %s | 대상 ETF: %s", config.KIS_ENV.upper(), config.ETF_SYMBOLS)
        logger.info("=" * 60)

        try:
            config.validate()
        except ValueError as e:
            logger.error("설정 오류: %s", e)
            return

        while True:
            try:
                if not is_market_open():
                    logger.info("장 외 시간 — 대기 중 (60초)")
                    time.sleep(60)
                    continue

                self._tick()

            except KeyboardInterrupt:
                logger.info("사용자 중단 요청 — 봇 종료")
                break
            except Exception as exc:
                logger.error("루프 오류: %s", exc, exc_info=True)
                time.sleep(10)

            time.sleep(config.POLL_INTERVAL)

    def _tick(self) -> None:
        """한 주기 처리"""
        for symbol in config.ETF_SYMBOLS:
            try:
                self._process_symbol(symbol)
            except Exception as exc:
                logger.warning("[%s] 처리 오류: %s", symbol, exc)

    def _process_symbol(self, symbol: str) -> None:
        # 1. 현재가 조회
        price_data = self.client.get_price(symbol)
        current_price = float(price_data.get("stck_prpr", 0))
        if current_price <= 0:
            logger.warning("[%s] 현재가 조회 실패", symbol)
            return

        # 2. 보유 포지션 익절/손절 먼저 처리
        if self.positions.has(symbol):
            exit_reason = self.positions.check_exit(symbol, current_price)
            if exit_reason in ("TAKE_PROFIT", "STOP_LOSS"):
                self._sell(symbol, current_price, exit_reason)
                return

        # 3. 일봉 데이터 조회 후 전략 평가
        ohlcv = self.client.get_daily_ohlcv(symbol, count=max(config.MA_LONG + 5, 30))
        if not ohlcv:
            logger.warning("[%s] 일봉 데이터 없음", symbol)
            return

        result = evaluate(symbol, ohlcv, current_price)
        logger.info(
            "[%s] 현재가=%d RSI=%.1f MA단기=%.0f MA장기=%.0f 거래량비율=%.2f → %s",
            symbol, current_price, result.rsi,
            result.ma_short, result.ma_long, result.volume_ratio,
            result.signal,
        )

        # 4. 전략 신호에 따른 매매 실행
        if result.signal == "BUY" and not self.positions.has(symbol):
            if is_new_buy_allowed():
                self._buy(symbol, current_price)

        elif result.signal == "SELL" and self.positions.has(symbol):
            self._sell(symbol, current_price, "STRATEGY_SELL")

    # ── 매수 ──────────────────────────────────────────────────────────────────

    def _buy(self, symbol: str, current_price: float) -> None:
        if self.positions.count() >= config.MAX_POSITIONS:
            logger.info("[%s] 최대 보유 종목 수 초과 — 매수 생략", symbol)
            return

        # 예산 결정: 최대 매수금액과 실제 매수가능금액 중 작은 값
        try:
            buyable = self.client.get_buyable_amount(symbol, int(current_price))
        except Exception as exc:
            logger.warning("[%s] 매수가능금액 조회 실패: %s — 기본 예산 사용", symbol, exc)
            buyable = config.MAX_BUY_AMOUNT

        budget = min(config.MAX_BUY_AMOUNT, buyable)
        quantity = calc_buy_quantity(current_price, budget)
        if quantity <= 0:
            logger.info("[%s] 매수 가능 수량 없음 (예산=%d)", symbol, budget)
            return

        try:
            self.client.buy(symbol, quantity)
            self.positions.add(symbol, current_price, quantity)
            logger.info(
                "[매수 완료] %s %d주 @ %.0f원 (예상 금액=%d원)",
                symbol, quantity, current_price, int(current_price * quantity),
            )
        except Exception as exc:
            logger.error("[%s] 매수 주문 실패: %s", symbol, exc)

    # ── 매도 ──────────────────────────────────────────────────────────────────

    def _sell(self, symbol: str, current_price: float, reason: str) -> None:
        pos = self.positions.get(symbol)
        if pos is None:
            return

        try:
            self.client.sell(symbol, pos.quantity)
            pnl_rate = pos.pnl_rate(current_price)
            logger.info(
                "[매도 완료] %s %d주 @ %.0f원 수익률=%.2f%% (%s)",
                symbol, pos.quantity, current_price, pnl_rate, reason,
            )
            self.positions.remove(symbol)
        except Exception as exc:
            logger.error("[%s] 매도 주문 실패: %s", symbol, exc)

    # ── 현황 출력 ──────────────────────────────────────────────────────────────

    def print_status(self) -> None:
        positions = self.positions.all()
        if not positions:
            logger.info("현재 보유 포지션 없음")
            return
        for pos in positions:
            try:
                price_data = self.client.get_price(pos.symbol)
                cur = float(price_data.get("stck_prpr", pos.avg_price))
            except Exception:
                cur = pos.avg_price
            logger.info(
                "포지션 | %s %d주 평단=%.0f 현재=%.0f 수익률=%.2f%%",
                pos.symbol, pos.quantity, pos.avg_price, cur,
                pos.pnl_rate(cur),
            )


def main() -> None:
    trader = Trader()
    trader.run()


if __name__ == "__main__":
    main()
