"""
한국투자증권 KIS Open API 기반 국내 ETF 단타 자동매매 프로그램
"""

import asyncio
import signal
import sys
from loguru import logger

from src.kis_api import KISAuth, KISClient, KISWebSocket
from src.strategy import ETFStrategy, StrategyConfig
from src.trader import AutoTrader
from src.utils import load_config, setup_logging, get_etf_list, validate_config


def build_trader(config: dict) -> AutoTrader:
    """설정값으로 AutoTrader 인스턴스 생성"""
    is_mock = config["kis"]["mock"]
    prefix = "mock" if is_mock else "real"

    app_key = config["kis"][f"{prefix}_app_key"]
    app_secret = config["kis"][f"{prefix}_app_secret"]
    base_url = config["kis"][f"{prefix}_base_url"]
    ws_url = config["kis"][f"{prefix}_ws_url"]
    account_no = config["kis"]["account_no"]
    account_product_code = config["kis"]["account_product_code"]

    auth = KISAuth(
        app_key=app_key,
        app_secret=app_secret,
        base_url=base_url,
        is_mock=is_mock,
    )
    client = KISClient(auth, account_no, account_product_code)
    ws = KISWebSocket(auth, ws_url)

    t_cfg = config["trading"]
    strategy_config = StrategyConfig(
        rsi_period=t_cfg.get("rsi_period", 14),
        rsi_oversold=t_cfg.get("rsi_oversold", 30),
        rsi_overbought=t_cfg.get("rsi_overbought", 70),
        ma_short=t_cfg.get("ma_short", 5),
        ma_long=t_cfg.get("ma_long", 20),
        bb_period=t_cfg.get("bb_period", 20),
        bb_std=t_cfg.get("bb_std", 2.0),
        volume_ratio_min=t_cfg.get("volume_ratio_min", 1.5),
        stop_loss_pct=t_cfg.get("stop_loss_pct", -1.5),
        take_profit_pct=t_cfg.get("take_profit_pct", 1.0),
        max_buy_amount=t_cfg.get("max_buy_amount", 500000),
        max_positions=t_cfg.get("max_positions", 3),
        max_daily_loss_pct=t_cfg.get("max_daily_loss_pct", -3.0),
    )
    strategy = ETFStrategy(strategy_config)

    etf_list = get_etf_list(config)

    return AutoTrader(
        client=client,
        ws=ws,
        strategy=strategy,
        etf_list=etf_list,
        market_open=t_cfg.get("market_open", "09:00"),
        market_close=t_cfg.get("market_close", "15:20"),
        pre_close_exit=t_cfg.get("pre_close_exit", "15:20"),
    )


async def main():
    config = load_config("config/config.yaml")
    setup_logging(config)

    logger.info("=" * 60)
    logger.info(" 한국투자증권 ETF 단타 자동매매 프로그램 시작")
    logger.info(" 모드: {}", "모의투자" if config["kis"]["mock"] else "실투자")
    logger.info("=" * 60)

    if not validate_config(config):
        logger.error("설정 파일을 확인하고 다시 실행해주세요.")
        sys.exit(1)

    trader = build_trader(config)

    # SIGINT / SIGTERM 처리
    loop = asyncio.get_running_loop()

    def shutdown():
        logger.info("종료 신호 수신")
        trader.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, shutdown)
        except NotImplementedError:
            # Windows에서는 add_signal_handler 미지원
            pass

    # WebSocket 사용 여부 (모의투자 환경에서는 REST 폴링 권장)
    use_websocket = not config["kis"]["mock"]

    await trader.run_async(use_websocket=use_websocket)


if __name__ == "__main__":
    asyncio.run(main())
