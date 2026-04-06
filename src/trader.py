"""
자동매매 실행 모듈

KIS API와 전략 모듈을 연결하여 실제 매매를 실행합니다.
장 운영 시간 관리, 주문 실행, 포지션 모니터링을 담당합니다.
"""

import asyncio
import time
from datetime import datetime
from typing import Optional
import pytz
from loguru import logger

from .kis_api import KISAuth, KISClient, KISWebSocket
from .strategy import ETFStrategy, StrategyConfig


KST = pytz.timezone("Asia/Seoul")


class AutoTrader:
    """ETF 자동매매 실행 클래스"""

    def __init__(
        self,
        client: KISClient,
        ws: KISWebSocket,
        strategy: ETFStrategy,
        etf_list: list[str],
        market_open: str = "09:00",
        market_close: str = "15:20",
        pre_close_exit: str = "15:20",
    ):
        self.client = client
        self.ws = ws
        self.strategy = strategy
        self.etf_list = etf_list
        self.market_open = market_open
        self.market_close = market_close
        self.pre_close_exit = pre_close_exit
        self._running = False
        self._last_price: dict[str, dict] = {}

    def _now_kst(self) -> datetime:
        return datetime.now(KST)

    def _is_market_open(self) -> bool:
        """현재 시장이 열려있는지 확인"""
        now = self._now_kst()
        if now.weekday() >= 5:  # 주말
            return False
        current_time = now.strftime("%H:%M")
        return self.market_open <= current_time <= self.market_close

    def _should_force_exit(self) -> bool:
        """장 마감 전 강제 청산 시간인지 확인"""
        now = self._now_kst()
        current_time = now.strftime("%H:%M")
        return current_time >= self.pre_close_exit

    def initialize(self):
        """매매 시작 전 초기화"""
        logger.info("=== 자동매매 초기화 시작 ===")

        # 잔고 조회
        try:
            balance = self.client.get_balance()
            logger.info(
                "잔고 조회 완료 | 예수금={:,}원 총평가={:,}원",
                balance["available_cash"], balance["total_eval_amount"]
            )
            self.strategy.initial_balance = balance["available_cash"]
        except Exception as e:
            logger.error("잔고 조회 실패: {}", e)

        # 종목별 가격 히스토리 로드
        for stock_code in self.etf_list:
            try:
                daily_prices = self.client.get_daily_prices(stock_code, period=30)
                self.strategy.init_price_buffer(stock_code, daily_prices)
                logger.info("시세 히스토리 로드 | {} ({} 일)", stock_code, len(daily_prices))
                time.sleep(0.2)  # API 호출 제한 방지
            except Exception as e:
                logger.warning("시세 히스토리 로드 실패 | {}: {}", stock_code, e)

        logger.info("=== 초기화 완료 | 모니터링 종목: {} ===", self.etf_list)

    def _on_price_update(self, price_data: dict):
        """실시간 가격 수신 시 처리 (동기 버전)"""
        stock_code = price_data["stock_code"]
        current_price = price_data["current_price"]
        self._last_price[stock_code] = price_data

        # 가격 버퍼 업데이트
        self.strategy.update_price(stock_code, price_data)

        # 매도 신호 먼저 확인
        if self.strategy.has_position(stock_code):
            should_sell, reason = self.strategy.check_sell_signal(stock_code, current_price)
            if should_sell:
                self._execute_sell(stock_code, current_price, reason)
                return

        # 매수 신호 확인
        if not self.strategy.has_position(stock_code) and self._is_market_open():
            if not self._should_force_exit():
                if self.strategy.check_buy_signal(stock_code, current_price):
                    self._execute_buy(stock_code, current_price)

    def _execute_buy(self, stock_code: str, current_price: int):
        """매수 실행"""
        try:
            balance = self.client.get_balance()
            available_cash = balance["available_cash"]
            quantity = self.strategy.calculate_buy_quantity(
                stock_code, current_price, available_cash
            )
            if quantity <= 0:
                logger.warning("매수 수량 부족 | {} 현재가={} 예수금={:,}", stock_code, current_price, available_cash)
                return

            order = self.client.place_order(
                stock_code=stock_code,
                order_type="buy",
                quantity=quantity,
                price=0,  # 시장가 매수
            )
            timestamp = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
            self.strategy.open_position(stock_code, quantity, current_price, timestamp)

        except Exception as e:
            logger.error("매수 실행 오류 | {}: {}", stock_code, e)

    def _execute_sell(self, stock_code: str, current_price: int, reason: str = ""):
        """매도 실행"""
        position = self.strategy.get_position(stock_code)
        if position is None:
            return
        try:
            order = self.client.place_order(
                stock_code=stock_code,
                order_type="sell",
                quantity=position.quantity,
                price=0,  # 시장가 매도
            )
            pnl = self.strategy.close_position(stock_code, current_price)
            if reason:
                logger.info("매도 사유: {}", reason)

        except Exception as e:
            logger.error("매도 실행 오류 | {}: {}", stock_code, e)

    def _force_exit_all(self):
        """보유 포지션 전체 강제 청산 (장 마감 전)"""
        positions = self.strategy.get_all_positions()
        if not positions:
            return

        logger.info("=== 장 마감 전 강제 청산 ({} 종목) ===", len(positions))
        for position in positions:
            stock_code = position.stock_code
            try:
                price_info = self.client.get_current_price(stock_code)
                current_price = price_info["current_price"]
                self._execute_sell(stock_code, current_price, reason="장 마감 전 강제 청산")
                time.sleep(0.3)
            except Exception as e:
                logger.error("강제 청산 실패 | {}: {}", stock_code, e)

    async def _price_monitor_loop(self):
        """WebSocket 실시간 시세 수신 루프"""
        # 콜백 등록
        for code in self.etf_list:
            self.ws.register_callback(code, self._on_price_update)

        while self._running:
            try:
                await self.ws.subscribe_realtime_price(self.etf_list)
            except Exception as e:
                logger.warning("WebSocket 연결 오류, 재연결 시도: {}", e)
                await asyncio.sleep(5)

    async def _polling_loop(self):
        """REST API 폴링 루프 (WebSocket 대체/보완)"""
        while self._running:
            try:
                if not self._is_market_open():
                    await asyncio.sleep(30)
                    continue

                # 강제 청산 확인
                if self._should_force_exit():
                    self._force_exit_all()
                    logger.info("오늘 매매 종료")
                    self._running = False
                    break

                # 종목별 현재가 조회 및 신호 처리
                for stock_code in self.etf_list:
                    try:
                        price_info = self.client.get_current_price(stock_code)
                        self._on_price_update(price_info)
                        await asyncio.sleep(0.5)
                    except Exception as e:
                        logger.warning("현재가 조회 실패 | {}: {}", stock_code, e)

                await asyncio.sleep(5)  # 5초마다 폴링

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("폴링 루프 오류: {}", e)
                await asyncio.sleep(10)

    def _print_status(self):
        """현재 포지션 및 수익 현황 출력"""
        now = self._now_kst().strftime("%Y-%m-%d %H:%M:%S")
        positions = self.strategy.get_all_positions()
        logger.info("─" * 60)
        logger.info("[{}] 보유 포지션: {}개 | 일별 누적손익: {:.2f}%",
                    now, len(positions), self.strategy.daily_pnl)
        for pos in positions:
            last = self._last_price.get(pos.stock_code, {})
            current = last.get("current_price", pos.avg_price)
            pnl_rate = (current - pos.avg_price) / pos.avg_price * 100
            logger.info("  {} | {}주 @{:.0f} → 현재:{} | P&L: {:.2f}%",
                        pos.stock_code, pos.quantity, pos.avg_price, current, pnl_rate)
        logger.info("─" * 60)

    async def _status_loop(self):
        """30초마다 현황 출력"""
        while self._running:
            await asyncio.sleep(30)
            self._print_status()

    async def run_async(self, use_websocket: bool = False):
        """비동기 매매 루프 실행"""
        self.initialize()
        self._running = True
        logger.info("=== 자동매매 시작 (모드: {}) ===",
                    "WebSocket" if use_websocket else "REST 폴링")

        tasks = [
            asyncio.create_task(self._status_loop()),
        ]
        if use_websocket:
            tasks.append(asyncio.create_task(self._price_monitor_loop()))
        else:
            tasks.append(asyncio.create_task(self._polling_loop()))

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            pass
        finally:
            self._running = False
            self._force_exit_all()
            logger.info("=== 자동매매 종료 ===")

    def stop(self):
        """매매 중지"""
        self._running = False
        logger.info("자동매매 중지 요청")
