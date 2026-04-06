"""
핵심 매매 로직 모듈 - 포지션 관리, 매수/매도 신호 판단
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import kis_api
import config

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """보유 포지션 정보"""
    code: str
    name: str
    qty: int
    avg_price: float
    entry_time: datetime = field(default_factory=datetime.now)

    @property
    def cost(self) -> float:
        return self.avg_price * self.qty

    def profit_rate(self, current_price: float) -> float:
        """수익률 계산 (수수료 미포함)"""
        if self.avg_price == 0:
            return 0.0
        return (current_price - self.avg_price) / self.avg_price


class Trader:
    """
    ETF 단타 자동매매 실행 클래스

    매수 조건:
        1. 현재가가 당일 시가 대비 +0.3% 이상 상승 (상승 추세 확인)
        2. 최근 1분 거래량이 직전 5분 평균 거래량의 2배 이상 (거래량 급증)
        3. 현재가가 20일 이동평균 대비 +0.5% 이상 (지지선 위)
        4. 동시 보유 포지션 수 < MAX_POSITIONS

    매도 조건:
        A. 목표 수익률 달성 (TARGET_PROFIT_RATE)
        B. 손절 라인 도달 (STOP_LOSS_RATE)
        C. 강제 청산 시각 도달 (FORCE_SELL_TIME)
    """

    def __init__(self) -> None:
        self.positions: dict[str, Position] = {}   # code → Position
        self.watchlist: list[dict] = []             # 관심 ETF 목록
        self.daily_trade_log: list[dict] = []       # 당일 매매 기록

    # ─── 관심 종목 관리 ────────────────────────────────────────

    def set_watchlist(self, etfs: list[dict]) -> None:
        self.watchlist = etfs
        logger.info(
            "관심 종목 등록: %s",
            ", ".join(f"{e['code']}({e['name']})" for e in etfs),
        )

    # ─── 매수 신호 판단 ────────────────────────────────────────

    def _check_buy_signal(self, etf: dict) -> tuple[bool, str]:
        """
        매수 신호 여부를 반환합니다.
        Returns:
            (True, 이유) 또는 (False, 이유)
        """
        code = etf["code"]

        # 이미 보유 중이면 추가 매수하지 않음
        if code in self.positions:
            return False, "이미 보유 중"

        # 최대 포지션 수 초과
        if len(self.positions) >= config.MAX_POSITIONS:
            return False, f"최대 보유 종목 수 초과 ({config.MAX_POSITIONS}개)"

        try:
            price_info = kis_api.get_price(code)
        except Exception as exc:
            return False, f"시세 조회 오류: {exc}"

        current_price = int(price_info.get("stck_prpr", "0"))
        open_price = int(price_info.get("stck_oprc", "0"))
        avg20 = float(price_info.get("d20_dsrt", "0"))     # 20일 이격도(%)

        if current_price == 0 or open_price == 0:
            return False, "가격 정보 없음"

        # 조건 1: 시가 대비 +0.3% 이상 상승
        rise_from_open = (current_price - open_price) / open_price
        if rise_from_open < 0.003:
            return False, f"시가 대비 상승률 미달 ({rise_from_open:.2%})"

        # 조건 2: 등락률 기준 거래량 급증 (현재 등락률 > 0.5%)
        change_rate = float(price_info.get("prdy_ctrt", "0"))
        if change_rate < 0.5:
            return False, f"등락률 미달 ({change_rate:.2f}%)"

        # 조건 3: 20일 이격도가 양수 (20일 이동평균 위)
        # d20_dsrt: 20일 이격도. 100 기준이므로 > 100이면 이평 위
        if avg20 > 0 and avg20 < 100.0:
            return False, f"20일 이평 아래 (이격도={avg20:.1f})"

        return True, f"매수 신호 (시가대비={rise_from_open:.2%}, 등락률={change_rate:.2f}%)"

    # ─── 매도 신호 판단 ────────────────────────────────────────

    def _check_sell_signal(
        self, position: Position, current_price: int, force_sell: bool = False
    ) -> tuple[bool, str]:
        """
        매도 신호 여부를 반환합니다.
        """
        if force_sell:
            return True, "강제 청산 (장 마감 전)"

        pnl = position.profit_rate(current_price)

        if pnl >= config.TARGET_PROFIT_RATE:
            return True, f"목표 수익률 달성 ({pnl:.2%})"

        if pnl <= -config.STOP_LOSS_RATE:
            return True, f"손절 ({pnl:.2%})"

        return False, f"보유 유지 (현재 수익률: {pnl:.2%})"

    # ─── 매수 실행 ─────────────────────────────────────────────

    def buy(self, etf: dict) -> bool:
        """시장가 매수 실행"""
        code = etf["code"]
        name = etf["name"]

        try:
            price_info = kis_api.get_price(code)
            current_price = int(price_info.get("stck_prpr", "0"))
        except Exception as exc:
            logger.error("[%s] 현재가 조회 실패: %s", code, exc)
            return False

        if current_price == 0:
            logger.warning("[%s] 현재가 0 - 매수 건너뜀", code)
            return False

        # 매수 수량 계산 (금액 기준)
        qty = config.MAX_POSITION_AMOUNT // current_price
        if qty < 1:
            logger.warning("[%s] 매수 가능 수량 없음 (현재가=%d, 한도=%d)", code, current_price, config.MAX_POSITION_AMOUNT)
            return False

        try:
            kis_api.place_order(code, "buy", qty, price=0)  # 시장가
        except Exception as exc:
            logger.error("[%s] 매수 주문 실패: %s", code, exc)
            return False

        self.positions[code] = Position(
            code=code, name=name, qty=qty, avg_price=current_price
        )
        self._log_trade("BUY", code, name, qty, current_price)
        logger.info("🟢 매수 체결: [%s] %s %d주 @%d원 (투자금=%d원)",
                    code, name, qty, current_price, qty * current_price)
        return True

    # ─── 매도 실행 ─────────────────────────────────────────────

    def sell(self, position: Position, reason: str = "") -> bool:
        """시장가 매도 실행"""
        code = position.code
        qty = position.qty

        try:
            kis_api.place_order(code, "sell", qty, price=0)  # 시장가
        except Exception as exc:
            logger.error("[%s] 매도 주문 실패: %s", code, exc)
            return False

        try:
            price_info = kis_api.get_price(code)
            current_price = int(price_info.get("stck_prpr", "0"))
        except Exception:
            current_price = int(position.avg_price)

        pnl_rate = position.profit_rate(current_price)
        pnl_amount = int((current_price - position.avg_price) * qty)
        self._log_trade("SELL", code, position.name, qty, current_price,
                        pnl_rate=pnl_rate, reason=reason)
        logger.info(
            "🔴 매도 체결: [%s] %s %d주 @%d원 | 손익=%+d원 (%+.2f%%) | 사유: %s",
            code, position.name, qty, current_price, pnl_amount, pnl_rate * 100, reason,
        )
        del self.positions[code]
        return True

    def sell_all(self, reason: str = "강제 청산") -> None:
        """전체 포지션 시장가 매도"""
        for pos in list(self.positions.values()):
            self.sell(pos, reason=reason)

    # ─── 메인 스캔 루프 ────────────────────────────────────────

    def scan_once(self, force_sell: bool = False) -> None:
        """
        한 사이클의 매수/매도 신호를 점검합니다.
        main.py의 스케줄러에서 주기적으로 호출됩니다.
        """
        # 1. 기존 포지션 매도 점검
        for pos in list(self.positions.values()):
            try:
                price_info = kis_api.get_price(pos.code)
                current_price = int(price_info.get("stck_prpr", "0"))
            except Exception as exc:
                logger.warning("[%s] 현재가 조회 실패: %s", pos.code, exc)
                continue

            should_sell, reason = self._check_sell_signal(pos, current_price, force_sell)
            if should_sell:
                self.sell(pos, reason=reason)

        if force_sell:
            return

        # 2. 관심 종목 매수 신호 점검
        for etf in self.watchlist:
            if etf["code"] in self.positions:
                continue
            should_buy, reason = self._check_buy_signal(etf)
            if should_buy:
                logger.info("[%s] 매수 신호: %s", etf["code"], reason)
                self.buy(etf)
            else:
                logger.debug("[%s] 매수 신호 없음: %s", etf["code"], reason)

    # ─── 매매 기록 ─────────────────────────────────────────────

    def _log_trade(
        self,
        action: str,
        code: str,
        name: str,
        qty: int,
        price: int,
        pnl_rate: float = 0.0,
        reason: str = "",
    ) -> None:
        self.daily_trade_log.append(
            {
                "time": datetime.now().isoformat(),
                "action": action,
                "code": code,
                "name": name,
                "qty": qty,
                "price": price,
                "pnl_rate": round(pnl_rate, 4),
                "reason": reason,
            }
        )

    def print_summary(self) -> None:
        """당일 매매 결과 요약 출력"""
        buys = [t for t in self.daily_trade_log if t["action"] == "BUY"]
        sells = [t for t in self.daily_trade_log if t["action"] == "SELL"]
        total_pnl = sum(t["pnl_rate"] for t in sells)
        logger.info("=" * 50)
        logger.info("당일 매매 결과 요약")
        logger.info("  매수 횟수: %d  /  매도 횟수: %d", len(buys), len(sells))
        if sells:
            avg_pnl = total_pnl / len(sells)
            wins = [t for t in sells if t["pnl_rate"] >= 0]
            logger.info(
                "  평균 수익률: %.2f%%  (승률: %d/%d)",
                avg_pnl * 100, len(wins), len(sells),
            )
        logger.info("=" * 50)
