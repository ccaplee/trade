"""
trader.py
─────────
포지션 관리 + 일간 리스크 관리 + 메인 매매 루프.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List

import pytz

from kis_api import KISClient, KISAPIError
from strategy import ScalpingStrategy, StrategyConfig

logger = logging.getLogger(__name__)

KST = pytz.timezone("Asia/Seoul")


def _now_kst() -> datetime:
    """현재 한국 시간(KST) 반환."""
    return datetime.now(KST)


# ──────────────────────────────────────────────────────────────
# 포지션 정보
# ──────────────────────────────────────────────────────────────

@dataclass
class Position:
    symbol: str
    qty: int
    entry_price: float
    entry_time: datetime = field(default_factory=_now_kst)


# ──────────────────────────────────────────────────────────────
# 일간 통계
# ──────────────────────────────────────────────────────────────

@dataclass
class DailyStats:
    date: date = field(default_factory=date.today)
    realized_pnl: float = 0.0
    trade_count: int = 0


# ──────────────────────────────────────────────────────────────
# 리스크 관리자
# ──────────────────────────────────────────────────────────────

class RiskManager:
    """일일 손실 한도 및 거래 상태 관리."""

    def __init__(self, daily_loss_limit: float, initial_equity: float) -> None:
        self.daily_loss_limit = daily_loss_limit   # 비율 (예: 0.02)
        self.initial_equity = initial_equity
        self._stats = DailyStats()
        self._halted = False

    def _reset_if_new_day(self) -> None:
        today = date.today()
        if self._stats.date != today:
            self._stats = DailyStats(date=today)
            self._halted = False
            logger.info("새로운 거래일 통계 초기화")

    def record_trade(self, pnl: float) -> None:
        self._reset_if_new_day()
        self._stats.realized_pnl += pnl
        self._stats.trade_count += 1
        logger.info(
            "거래 기록: PnL=%.0f원 | 누적=%.0f원 | 횟수=%d",
            pnl, self._stats.realized_pnl, self._stats.trade_count,
        )
        loss_ratio = -self._stats.realized_pnl / max(self.initial_equity, 1)
        if loss_ratio >= self.daily_loss_limit:
            self._halted = True
            logger.warning(
                "일일 손실 한도 초과 (%.2f%%). 금일 거래 중단.",
                loss_ratio * 100,
            )

    @property
    def is_halted(self) -> bool:
        self._reset_if_new_day()
        return self._halted

    @property
    def daily_pnl(self) -> float:
        self._reset_if_new_day()
        return self._stats.realized_pnl

    @property
    def trade_count(self) -> int:
        self._reset_if_new_day()
        return self._stats.trade_count


# ──────────────────────────────────────────────────────────────
# 메인 Trader
# ──────────────────────────────────────────────────────────────

class ETFScalpingTrader:
    """KIS API 기반 ETF 단타 자동매매 트레이더."""

    def __init__(
        self,
        client: KISClient,
        strategy: ScalpingStrategy,
        etf_universe: List[str],
        scan_interval: int = 10,
        market_open: str = "09:00",
        market_close: str = "15:20",
    ) -> None:
        self.client = client
        self.strategy = strategy
        self.etf_universe = etf_universe
        self.scan_interval = scan_interval
        self.market_open = market_open
        self.market_close = market_close

        self._positions: Dict[str, Position] = {}
        self._risk: RiskManager | None = None

    # ── 초기화 ─────────────────────────────────────────────────

    def initialize(self) -> None:
        """잔고 조회로 초기 자산 파악 후 리스크 관리자 설정."""
        cash = self.client.get_available_cash()
        logger.info("초기 주문 가능 현금: %d원", cash)
        self._risk = RiskManager(
            daily_loss_limit=self.strategy.cfg.daily_loss_limit,
            initial_equity=max(cash, 1),
        )

    # ── 운영 시간 확인 ─────────────────────────────────────────

    def _is_market_hours(self) -> bool:
        now = datetime.now(KST)
        open_h, open_m = map(int, self.market_open.split(":"))
        close_h, close_m = map(int, self.market_close.split(":"))
        market_start = now.replace(hour=open_h, minute=open_m, second=0, microsecond=0)
        market_end = now.replace(hour=close_h, minute=close_m, second=0, microsecond=0)
        return market_start <= now <= market_end

    def _is_weekday(self) -> bool:
        return datetime.now(KST).weekday() < 5

    # ── 현재가 조회 ────────────────────────────────────────────

    def _fetch_price(self, symbol: str) -> float | None:
        try:
            data = self.client.get_price(symbol)
            price_str = data.get("stck_prpr") or data.get("stck_oprc", "0")
            return float(price_str)
        except (KISAPIError, ValueError, KeyError) as exc:
            logger.warning("[%s] 현재가 조회 실패: %s", symbol, exc)
            return None

    # ── 매수 실행 ──────────────────────────────────────────────

    def _execute_buy(self, symbol: str, price: float) -> None:
        if symbol in self._positions:
            return
        if self._risk and self._risk.is_halted:
            return

        cash = self.client.get_available_cash()
        qty = self.strategy.calc_qty(cash, price)
        if qty <= 0:
            logger.info("[%s] 매수 수량 0 → 스킵", symbol)
            return

        try:
            self.client.buy_market(symbol, qty)
            self._positions[symbol] = Position(
                symbol=symbol, qty=qty, entry_price=price
            )
            logger.info("[%s] 매수 체결: %d주 @ %.0f원", symbol, qty, price)
        except KISAPIError as exc:
            logger.error("[%s] 매수 주문 실패: %s", symbol, exc)

    # ── 매도 실행 ──────────────────────────────────────────────

    def _execute_sell(self, symbol: str, current_price: float, reason: str) -> None:
        pos = self._positions.get(symbol)
        if pos is None:
            return

        try:
            self.client.sell_market(symbol, pos.qty)
            pnl = (current_price - pos.entry_price) * pos.qty
            logger.info(
                "[%s] 매도 체결: %d주 @ %.0f원 | PnL=%.0f원 (%s)",
                symbol, pos.qty, current_price, pnl, reason,
            )
            if self._risk:
                self._risk.record_trade(pnl)
            del self._positions[symbol]
        except KISAPIError as exc:
            logger.error("[%s] 매도 주문 실패: %s", symbol, exc)

    # ── 전량 청산 ──────────────────────────────────────────────

    def liquidate_all(self, reason: str = "강제 청산") -> None:
        """보유 중인 모든 포지션을 시장가로 청산."""
        if not self._positions:
            return
        logger.info("전체 포지션 청산 시작: %s", reason)
        for symbol, pos in list(self._positions.items()):
            price = self._fetch_price(symbol) or pos.entry_price
            self._execute_sell(symbol, price, reason)

    # ── 단일 종목 처리 ─────────────────────────────────────────

    def _process_symbol(self, symbol: str) -> None:
        price = self._fetch_price(symbol)
        if price is None or price <= 0:
            return

        # 히스토리 업데이트
        self.strategy.update_price(symbol, price)

        if symbol in self._positions:
            # 보유 중 → 청산 여부 확인
            pos = self._positions[symbol]
            sig = self.strategy.exit_signal(symbol, pos.entry_price, price)
            if sig.action == "SELL":
                self._execute_sell(symbol, price, sig.reason)
        else:
            # 미보유 → 진입 여부 확인
            if self._risk and self._risk.is_halted:
                return
            sig = self.strategy.entry_signal(symbol, len(self._positions))
            if sig.action == "BUY":
                logger.info("[%s] 매수 신호: %s (가격=%.0f)", symbol, sig.reason, price)
                self._execute_buy(symbol, price)

    # ── 메인 루프 ──────────────────────────────────────────────

    def run(self) -> None:
        """장 시간 동안 ETF 유니버스를 순환 스캔."""
        logger.info("=== ETF 단타 자동매매 시작 ===")
        self.initialize()

        try:
            while True:
                if not self._is_weekday():
                    logger.info("주말 – 대기 중...")
                    time.sleep(60)
                    continue

                if not self._is_market_hours():
                    # 장 마감 후 잔여 포지션 청산
                    if self._positions:
                        self.liquidate_all("장 마감 청산")
                    now_str = datetime.now(KST).strftime("%H:%M:%S")
                    logger.info("[%s] 장 외 시간 – 대기 중...", now_str)
                    time.sleep(30)
                    continue

                # 리스크 한도 초과 시 포지션 청산 후 대기
                if self._risk and self._risk.is_halted:
                    if self._positions:
                        self.liquidate_all("일일 손실 한도 초과 청산")
                    time.sleep(60)
                    continue

                # ETF 유니버스 스캔
                for symbol in self.etf_universe:
                    self._process_symbol(symbol)
                    time.sleep(0.2)   # 의도적 스로틀링: 초당 5건 (API 최대 20건 대비 보수적 설정)

                # 현황 로그
                logger.info(
                    "[현황] 보유=%d종목 | 일간PnL=%.0f원 | 거래횟수=%d",
                    len(self._positions),
                    self._risk.daily_pnl if self._risk else 0,
                    self._risk.trade_count if self._risk else 0,
                )

                time.sleep(self.scan_interval)

        except KeyboardInterrupt:
            logger.info("사용자 중단 – 포지션 정리 중...")
            self.liquidate_all("프로그램 종료")
            logger.info("=== 자동매매 종료 ===")
