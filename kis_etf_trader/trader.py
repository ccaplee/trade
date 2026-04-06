"""
메인 트레이딩 루프
장 운영 시간 내에 ETF 선별 → 매수 신호 확인 → 익절/손절을 반복합니다.
"""

import time
from datetime import datetime

import schedule

from .api_client import KISClient
from .config import Config
from .etf_selector import select_top_etfs
from .logger import setup_logger
from .risk_manager import RiskManager
from .strategy import TradingStrategy

logger = setup_logger(__name__)


def _now_str() -> str:
    return datetime.now().strftime("%H:%M")


def _is_market_open() -> bool:
    now = _now_str()
    return Config.MARKET_OPEN <= now < Config.MARKET_CLOSE


class Trader:
    """자동매매 메인 컨트롤러."""

    def __init__(self) -> None:
        self._client = KISClient()
        self._risk_manager = RiskManager()
        self._strategy = TradingStrategy(self._client, self._risk_manager)
        self._watchlist: list[str] = []

    # ------------------------------------------------------------------
    # 스케줄 작업
    # ------------------------------------------------------------------

    def _refresh_watchlist(self) -> None:
        """ETF 관심 종목 목록을 갱신합니다."""
        if not _is_market_open():
            return
        logger.info("=== ETF 관심 종목 갱신 시작 ===")
        new_list = select_top_etfs(self._client)
        if new_list:
            self._watchlist = new_list
            logger.info("관심 종목: %s", ", ".join(self._watchlist))
        else:
            logger.warning("ETF 선별 결과가 없습니다. 기존 목록을 유지합니다.")

    def _trading_cycle(self) -> None:
        """매 분봉마다 실행되는 매매 사이클."""
        if not _is_market_open():
            return

        if not self._watchlist:
            logger.info("관심 종목 없음 — 사이클 스킵")
            return

        # 1. 보유 종목 익절·손절 먼저 확인
        for ticker in list(self._risk_manager.all_tickers()):
            self._strategy.check_and_sell(ticker)

        # 2. 관심 종목 매수 신호 확인
        for ticker in self._watchlist:
            if self._risk_manager.position_count() >= Config.MAX_POSITIONS:
                break
            self._strategy.try_buy(ticker)

        # 3. 현재 포지션 로그
        price_map: dict[str, float] = {}
        for ticker in self._risk_manager.all_tickers():
            try:
                info = self._client.get_price(ticker)
                price_map[ticker] = float(info.get("stck_prpr", 0))
            except Exception:
                pass
        self._risk_manager.log_positions(price_map)

    # ------------------------------------------------------------------
    # 장 마감 처리
    # ------------------------------------------------------------------

    def _close_all_positions(self) -> None:
        """장 마감 전 모든 포지션을 청산합니다."""
        tickers = self._risk_manager.all_tickers()
        if not tickers:
            return
        logger.info("=== 장 마감 전 전량 청산 시작 ===")
        for ticker in tickers:
            pos = self._risk_manager.get_position(ticker)
            if pos is None:
                continue
            try:
                self._client.sell_market_order(ticker, pos.qty)
                self._risk_manager.close_position(ticker)
                logger.info("[%s] 마감 청산 완료", ticker)
            except Exception as exc:
                logger.error("[%s] 마감 청산 실패: %s", ticker, exc)

    # ------------------------------------------------------------------
    # 실행
    # ------------------------------------------------------------------

    def run(self) -> None:
        """스케줄러를 등록하고 메인 루프를 시작합니다."""
        logger.info("=== KIS ETF 자동매매 시작 ===")
        logger.info("모드: %s", "실전" if Config.IS_REAL else "모의")
        logger.info("익절: +%.1f%% | 손절: -%.1f%%", Config.TAKE_PROFIT_PCT, Config.STOP_LOSS_PCT)

        # ETF 선별: 장 시작 5분 후 최초 실행, 이후 10분마다 갱신
        schedule.every(Config.SCREENING_INTERVAL_MIN).minutes.do(self._refresh_watchlist)

        # 매매 사이클: 5분마다 실행 (5분봉 기준)
        schedule.every(Config.CANDLE_INTERVAL_MIN).minutes.do(self._trading_cycle)

        # 장 마감 직전 청산 (15:25)
        schedule.every().day.at("15:25").do(self._close_all_positions)

        # 최초 즉시 ETF 선별 (장 시작 이후라면)
        now = _now_str()
        if Config.SCREENING_START <= now < Config.MARKET_CLOSE:
            self._refresh_watchlist()

        logger.info("스케줄러 시작 — 매매 사이클: %d분마다, ETF 갱신: %d분마다",
                    Config.CANDLE_INTERVAL_MIN, Config.SCREENING_INTERVAL_MIN)

        while True:
            schedule.run_pending()
            time.sleep(1)
