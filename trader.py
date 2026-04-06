"""
trader.py
─────────
메인 자동매매 루프

실행 방법
  $ python trader.py

흐름
  1. KIS 토큰 초기화
  2. 매 LOOP_INTERVAL_SEC 마다:
     a. 장 운영 시간 확인
     b. 계좌 잔고 조회 → 포지션 동기화
     c. 강제 청산 시각 도달 시 전 종목 시장가 청산
     d. 종목별 분봉 차트 조회 → 전략 신호 판단 → 주문 실행
"""

from __future__ import annotations

import time

import config
import strategy as strat
import utils
from kis_api import KISApiError, KISClient
from strategy import Signal, StrategyState

logger = utils.setup_logger()


def _sync_positions(client: KISClient, state: StrategyState) -> int:
    """
    계좌 잔고를 조회해 strategy 상태(포지션)를 동기화하고
    주문 가능 현금을 반환합니다.
    """
    try:
        balance = client.get_balance()
    except KISApiError as e:
        logger.error("잔고 조회 실패: %s", e)
        return 0

    # 전략 포지션을 실제 잔고 기준으로 갱신
    held_symbols = {p["symbol"] for p in balance["positions"]}

    # 청산된 종목 제거
    for sym in list(state.positions.keys()):
        if sym not in held_symbols:
            logger.info("[%s] 포지션 청산 확인 → 상태에서 제거", sym)
            del state.positions[sym]

    # 보유 종목 동기화
    for pos in balance["positions"]:
        sym = pos["symbol"]
        state.positions[sym] = strat.Position(
            symbol=sym,
            qty=pos["qty"],
            avg_price=pos["avg_price"],
            name=pos["name"],
        )

    cash = balance["cash"]
    logger.info(
        "잔고 동기화 완료 | 예수금=%d원 | 보유종목=%d개",
        cash,
        len(state.positions),
    )
    return cash


def _force_sell_all(client: KISClient, state: StrategyState) -> None:
    """장 마감 전 미청산 포지션을 시장가로 전량 매도합니다."""
    for sym, pos in list(state.positions.items()):
        logger.info("[%s] 강제 청산: %d주 시장가 매도", sym, pos.qty)
        try:
            client.sell_order(sym, pos.qty, price=0)
        except KISApiError as e:
            logger.error("[%s] 강제 청산 실패: %s", sym, e)


def _process_symbol(
    client: KISClient,
    state: StrategyState,
    symbol: str,
    cash: int,
) -> None:
    """종목 한 개에 대한 신호 판단 및 주문 실행"""
    try:
        current_price = client.get_current_price(symbol)
    except KISApiError as e:
        logger.error("[%s] 현재가 조회 실패: %s", symbol, e)
        return

    try:
        raw_bars = client.get_minute_chart(symbol, time_div="1")
    except KISApiError as e:
        logger.error("[%s] 분봉 차트 조회 실패: %s", symbol, e)
        return

    signal = strat.evaluate(symbol, raw_bars, state, current_price)

    if signal == Signal.BUY:
        # 이미 보유 중이면 추가 매수 금지
        if symbol in state.positions:
            logger.debug("[%s] 이미 보유 중 → 추가 매수 생략", symbol)
            return

        qty = strat.calc_order_qty(cash, current_price)
        if qty <= 0:
            logger.warning("[%s] 매수 수량 0 → 주문 생략 (예수금 부족?)", symbol)
            return

        try:
            client.buy_order(symbol, qty, price=0)  # 시장가 매수
            # 낙관적 포지션 기록 (다음 싱크 전까지 활용)
            state.positions[symbol] = strat.Position(
                symbol=symbol,
                qty=qty,
                avg_price=float(current_price),
            )
        except KISApiError as e:
            logger.error("[%s] 매수 주문 실패: %s", symbol, e)

    elif signal == Signal.SELL:
        pos = state.positions.get(symbol)
        if not pos:
            logger.debug("[%s] 보유 포지션 없음 → 매도 생략", symbol)
            return

        try:
            client.sell_order(symbol, pos.qty, price=0)  # 시장가 매도
            del state.positions[symbol]
        except KISApiError as e:
            logger.error("[%s] 매도 주문 실패: %s", symbol, e)


def run() -> None:
    logger.info("=" * 60)
    logger.info("KIS ETF 자동매매 봇 시작 (환경: %s)", config.ENV)
    logger.info("대상 종목: %s", config.ETF_SYMBOLS)
    logger.info("=" * 60)

    client = KISClient()
    state = StrategyState()

    while True:
        now_str = utils.now_kst().strftime("%H:%M:%S")

        # ── 강제 청산 시각 확인 ─────────────────────────────────────────────────
        if utils.is_force_sell_time():
            if state.positions:
                logger.info("[%s] 강제 청산 시각 도달 → 전 종목 청산", now_str)
                _force_sell_all(client, state)
            logger.info("장 마감. 봇을 종료합니다.")
            break

        # ── 장 운영 시간 외 대기 ────────────────────────────────────────────────
        if not utils.is_market_open():
            logger.info("[%s] 장 운영 시간 외. %d초 대기...", now_str, config.LOOP_INTERVAL_SEC)
            time.sleep(config.LOOP_INTERVAL_SEC)
            continue

        # ── 잔고 동기화 ─────────────────────────────────────────────────────────
        cash = _sync_positions(client, state)

        # ── 종목별 전략 실행 ────────────────────────────────────────────────────
        for symbol in config.ETF_SYMBOLS:
            _process_symbol(client, state, symbol, cash)

        logger.info("[%s] 루프 완료. %d초 대기...", now_str, config.LOOP_INTERVAL_SEC)
        time.sleep(config.LOOP_INTERVAL_SEC)


if __name__ == "__main__":
    run()
