"""
메인 트레이더 모듈

실행 흐름:
  1. 장 개장 대기
  2. 개장 후 일정 시간 대기 (초기 변동성 확인)
  3. ETF 스크리닝 (상위 5개 선별)
  4. 각 ETF의 전일 데이터 수집 (변동성 돌파 기준)
  5. 루프: 현재가 조회 → 매수/매도 판단 → 주문 실행
  6. 강제 청산 시간 도달 시 전량 시장가 매도
  7. 일일 거래 결과 리포트 출력
"""
import logging
import time
from datetime import datetime, timedelta

from .kis_auth import KISAuth
from .kis_api import KISApi
from .etf_screener import EtfScreener, EtfCandidate
from .strategy import Strategy, Position

logger = logging.getLogger(__name__)

# 트레이더 설정
SCREEN_DELAY_MINUTES = 10   # 개장 후 스크리닝 대기 시간 (분)
MONITOR_INTERVAL = 10        # 모니터링 루프 간격 (초)
MAX_POSITIONS = 5            # 동시 최대 보유 종목 수
DAILY_LOSS_LIMIT = -3.0      # 일일 손실 한도 (%)


class Trader:
    """KIS ETF 단타 자동매매 트레이더"""

    def __init__(self):
        self.auth = KISAuth()
        self.api = KISApi(self.auth)
        self.screener = EtfScreener(self.api)
        self.strategy = Strategy()

        self.positions: dict[str, Position] = {}
        self.etf_candidates: list[EtfCandidate] = []
        self.prev_data: dict[str, dict] = {}  # 전일 OHLCV 캐시

        self.initial_cash = 0
        self.realized_pnl = 0.0
        self.trade_log: list[dict] = []

    # ------------------------------------------------------------------
    # 초기화
    # ------------------------------------------------------------------

    def _init_capital(self) -> None:
        """초기 예수금을 기록합니다."""
        self.initial_cash = self.api.get_available_cash()
        logger.info("주문 가능 현금: %s원", f"{self.initial_cash:,}")

    def _load_prev_data(self, code: str) -> dict:
        """종목의 전일 고/저가를 조회합니다."""
        if code in self.prev_data:
            return self.prev_data[code]
        try:
            chart = self.api.get_price_chart(code, "D")
            if len(chart) >= 2:
                # output2[0]은 당일, [1]은 전일
                prev = chart[1]
                data = {
                    "prev_high": int(prev.get("stck_hgpr", "0")),
                    "prev_low": int(prev.get("stck_lwpr", "0")),
                }
            else:
                data = {"prev_high": 0, "prev_low": 0}
        except Exception as exc:
            logger.warning("전일 데이터 조회 실패 (%s): %s", code, exc)
            data = {"prev_high": 0, "prev_low": 0}
        self.prev_data[code] = data
        return data

    # ------------------------------------------------------------------
    # 매수 / 매도
    # ------------------------------------------------------------------

    def _try_buy(self, candidate: EtfCandidate) -> None:
        """매수 조건 확인 후 시장가 매수를 실행합니다."""
        code = candidate.code
        if code in self.positions:
            return
        if len(self.positions) >= MAX_POSITIONS:
            return

        try:
            price_info = self.api.get_price(code)
            current_price = int(price_info.get("stck_prpr", "0"))
            open_price = int(price_info.get("stck_oprc", "0") or "0")
        except Exception as exc:
            logger.warning("현재가 조회 실패 (%s): %s", code, exc)
            return

        prev = self._load_prev_data(code)

        if not self.strategy.should_buy(
            current_price, open_price, prev["prev_high"], prev["prev_low"]
        ):
            return

        available = self.api.get_available_cash()
        # 총 자산 = 현금 + 현재 보유 포지션의 평가금액
        holdings_value = sum(
            int(p.buy_price * p.qty) for p in self.positions.values()
        )
        total_asset = available + holdings_value
        qty = self.strategy.calc_buy_qty(available, current_price, total_asset)
        if qty <= 0:
            logger.info("[%s] 매수 수량 부족, 건너뜀", code)
            return

        try:
            result = self.api.buy_market(code, qty)
            if result.get("rt_cd") != "0":
                logger.error("[%s] 매수 주문 실패: %s", code, result.get("msg1"))
                return

            position = Position(
                code=code,
                name=candidate.name,
                qty=qty,
                buy_price=float(current_price),
            )
            self.positions[code] = position
            self.trade_log.append(
                {
                    "time": datetime.now().isoformat(),
                    "action": "BUY",
                    "code": code,
                    "name": candidate.name,
                    "qty": qty,
                    "price": current_price,
                }
            )
            logger.info(
                "[매수] [%s] %s %d주 @%d원 (익절: %.0f / 손절: %.0f)",
                code, candidate.name, qty, current_price,
                position.profit_target_price, position.stop_loss_price,
            )
        except Exception as exc:
            logger.error("[%s] 매수 주문 예외: %s", code, exc)

    def _try_sell(self, code: str, reason: str) -> None:
        """보유 포지션을 시장가 매도합니다."""
        position = self.positions.get(code)
        if not position:
            return

        try:
            price_info = self.api.get_price(code)
            current_price = int(price_info.get("stck_prpr", "0"))
        except Exception as exc:
            logger.warning("현재가 조회 실패 (%s): %s", code, exc)
            current_price = 0

        try:
            result = self.api.sell_market(code, position.qty)
            if result.get("rt_cd") != "0":
                logger.error("[%s] 매도 주문 실패: %s", code, result.get("msg1"))
                return

            pnl = (current_price - position.buy_price) * position.qty
            self.realized_pnl += pnl
            self.trade_log.append(
                {
                    "time": datetime.now().isoformat(),
                    "action": "SELL",
                    "code": code,
                    "name": position.name,
                    "qty": position.qty,
                    "price": current_price,
                    "pnl": pnl,
                    "reason": reason,
                }
            )
            logger.info(
                "[매도/%s] [%s] %s %d주 @%d원 PnL=%.0f원",
                reason, code, position.name, position.qty, current_price, pnl,
            )
            del self.positions[code]
        except Exception as exc:
            logger.error("[%s] 매도 주문 예외: %s", code, exc)

    def _force_close_all(self) -> None:
        """모든 포지션을 강제 청산합니다."""
        if not self.positions:
            return
        logger.info("강제 청산 시작 (보유 %d종목)", len(self.positions))
        for code in list(self.positions.keys()):
            self._try_sell(code, "강제청산")

    # ------------------------------------------------------------------
    # 모니터링 루프
    # ------------------------------------------------------------------

    def _monitor_loop(self) -> None:
        """보유 포지션의 익절/손절 여부를 주기적으로 확인합니다."""
        logger.info("모니터링 루프 시작 (간격: %d초)", MONITOR_INTERVAL)
        while True:
            # 강제 청산 시간 확인
            if self.strategy.should_force_close():
                self._force_close_all()
                break

            if not self.strategy.is_trading_time():
                logger.info("거래 시간 외 – 대기 중...")
                time.sleep(60)
                continue

            # 일일 손실 한도 확인 (실현 + 미실현 손익 포함)
            if self.initial_cash > 0:
                unrealized_pnl = 0.0
                for pos in list(self.positions.values()):
                    try:
                        pi = self.api.get_price(pos.code)
                        cur = int(pi.get("stck_prpr", "0"))
                        unrealized_pnl += (cur - pos.buy_price) * pos.qty
                    except Exception:
                        pass
                total_pnl_pct = (self.realized_pnl + unrealized_pnl) / self.initial_cash * 100
                if total_pnl_pct <= DAILY_LOSS_LIMIT:
                    logger.warning(
                        "일일 손실 한도 도달 (%.2f%%) – 전량 청산 후 거래 중단", total_pnl_pct
                    )
                    self._force_close_all()
                    break

            # 보유 포지션 모니터링
            for code in list(self.positions.keys()):
                position = self.positions.get(code)
                if not position:
                    continue
                try:
                    price_info = self.api.get_price(code)
                    current_price = int(price_info.get("stck_prpr", "0"))
                except Exception as exc:
                    logger.warning("현재가 조회 실패 (%s): %s", code, exc)
                    continue

                if self.strategy.should_take_profit(current_price, position):
                    self._try_sell(code, "익절")
                elif self.strategy.should_stop_loss(current_price, position):
                    self._try_sell(code, "손절")

            # 신규 매수 시도 (포지션 여유 있을 때)
            if len(self.positions) < MAX_POSITIONS:
                for candidate in self.etf_candidates:
                    if candidate.code not in self.positions:
                        self._try_buy(candidate)

            time.sleep(MONITOR_INTERVAL)

    # ------------------------------------------------------------------
    # 리포트
    # ------------------------------------------------------------------

    def _print_report(self) -> None:
        """일일 거래 결과를 출력합니다."""
        logger.info("=" * 60)
        logger.info("[ 일일 거래 결과 리포트 ]")
        logger.info("  총 실현 손익: %s원", f"{self.realized_pnl:,.0f}")
        if self.initial_cash > 0:
            pnl_pct = self.realized_pnl / self.initial_cash * 100
            logger.info("  수익률: %.2f%%", pnl_pct)
        logger.info("  거래 횟수: %d건", len(self.trade_log))
        for log in self.trade_log:
            pnl_str = f"  PnL={log['pnl']:,.0f}원" if "pnl" in log else ""
            reason_str = f"  ({log['reason']})" if "reason" in log else ""
            logger.info(
                "  [%s] %s [%s] %s %d주 @%d원%s%s",
                log["time"][:19],
                log["action"],
                log["code"],
                log["name"],
                log["qty"],
                log["price"],
                pnl_str,
                reason_str,
            )
        logger.info("=" * 60)

    # ------------------------------------------------------------------
    # 실행 진입점
    # ------------------------------------------------------------------

    def run(self) -> None:
        """자동매매를 시작합니다."""
        logger.info("KIS ETF 단타 자동매매 시작")

        # 시장 개장 대기
        while not self.strategy.is_market_open():
            now = datetime.now()
            if now.weekday() >= 5:
                logger.info("오늘은 휴장일(주말)입니다. 내일 다시 실행하세요.")
                return
            open_time = now.replace(hour=9, minute=0, second=0, microsecond=0)
            if now < open_time:
                wait_sec = int((open_time - now).total_seconds())
                logger.info("장 개장까지 %d분 대기...", wait_sec // 60)
                time.sleep(min(wait_sec, 60))
            else:
                break

        # 초기 예수금 조회
        self._init_capital()
        if self.initial_cash <= 0:
            logger.error("주문 가능 현금이 없습니다. 프로그램을 종료합니다.")
            return

        # 개장 직후 변동성 안정화 대기
        screen_after = datetime.now().replace(
            hour=9, minute=SCREEN_DELAY_MINUTES, second=0, microsecond=0
        )
        now = datetime.now()
        if now < screen_after:
            wait_sec = int((screen_after - now).total_seconds())
            logger.info("개장 초기 변동성 안정화 대기: %d분...", wait_sec // 60 + 1)
            time.sleep(wait_sec)

        # ETF 스크리닝
        self.etf_candidates = self.screener.screen()
        if not self.etf_candidates:
            logger.warning("선별된 ETF가 없습니다. 프로그램을 종료합니다.")
            return

        # 전일 데이터 사전 로딩
        for candidate in self.etf_candidates:
            self._load_prev_data(candidate.code)

        # 모니터링 루프 진입
        try:
            self._monitor_loop()
        except KeyboardInterrupt:
            logger.info("사용자 중단 요청 – 보유 포지션 청산 중...")
            self._force_close_all()
        finally:
            self._print_report()
            self.auth.revoke_token()
            logger.info("프로그램 종료")
