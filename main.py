"""
main.py
───────
진입점.  환경변수 / .env 파일을 읽어 KIS API 클라이언트와 전략을 초기화한 뒤
ETFScalpingTrader 를 실행합니다.

실행 방법:
    python main.py

종료:
    Ctrl+C  →  보유 포지션 전량 청산 후 종료
"""

from __future__ import annotations

import logging
import os
import sys

import yaml
from dotenv import load_dotenv

from kis_api import KISClient
from strategy import ScalpingStrategy, StrategyConfig
from trader import ETFScalpingTrader


# ──────────────────────────────────────────────────────────────
# 로거 설정
# ──────────────────────────────────────────────────────────────

def _setup_logging(level: str = "INFO") -> None:
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=fmt,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("trading.log", encoding="utf-8"),
        ],
    )


# ──────────────────────────────────────────────────────────────
# 설정 로드
# ──────────────────────────────────────────────────────────────

def _load_config(path: str = "config.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _require_env(key: str) -> str:
    val = os.getenv(key)
    if not val:
        print(f"[오류] 환경변수 '{key}' 가 설정되지 않았습니다.")
        print("  .env 파일을 생성하거나 환경변수로 직접 설정하세요.")
        print("  참고: .env.example")
        sys.exit(1)
    return val


# ──────────────────────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────────────────────

def main() -> None:
    load_dotenv()

    log_level = os.getenv("LOG_LEVEL", "INFO")
    _setup_logging(log_level)

    logger = logging.getLogger(__name__)

    # 설정 파일 로드
    cfg = _load_config()
    strategy_cfg_raw: dict = cfg.get("strategy", {})
    schedule_cfg: dict = cfg.get("schedule", {})
    etf_universe: list[str] = cfg.get("etf_universe", [])

    if not etf_universe:
        logger.error("config.yaml 에 etf_universe 가 비어있습니다.")
        sys.exit(1)

    # 환경변수 (필수)
    app_key    = _require_env("KIS_APP_KEY")
    app_secret = _require_env("KIS_APP_SECRET")
    account_no = _require_env("KIS_ACCOUNT_NO")
    is_mock    = os.getenv("KIS_IS_MOCK", "true").lower() != "false"

    logger.info("모드: %s", "모의투자" if is_mock else "실계좌 ⚠️")

    # KIS 클라이언트
    client = KISClient(
        app_key=app_key,
        app_secret=app_secret,
        account_no=account_no,
        is_mock=is_mock,
    )

    # 전략 설정
    strategy_cfg = StrategyConfig(
        momentum_period    = strategy_cfg_raw.get("momentum_period",    5),
        momentum_threshold = strategy_cfg_raw.get("momentum_threshold", 0.003),
        rsi_period         = strategy_cfg_raw.get("rsi_period",         14),
        rsi_oversold       = strategy_cfg_raw.get("rsi_oversold",       35.0),
        rsi_overbought     = strategy_cfg_raw.get("rsi_overbought",     65.0),
        take_profit        = strategy_cfg_raw.get("take_profit",        0.005),
        stop_loss          = strategy_cfg_raw.get("stop_loss",          0.003),
        max_positions      = strategy_cfg_raw.get("max_positions",      3),
        position_size      = strategy_cfg_raw.get("position_size",      0.2),
        daily_loss_limit   = strategy_cfg_raw.get("daily_loss_limit",   0.02),
        max_trade_amount   = strategy_cfg_raw.get("max_trade_amount",   1_000_000),
        price_history_bars = schedule_cfg.get("price_history_bars",     60),
    )
    strategy = ScalpingStrategy(strategy_cfg)

    # 트레이더
    trader = ETFScalpingTrader(
        client        = client,
        strategy      = strategy,
        etf_universe  = etf_universe,
        scan_interval = schedule_cfg.get("scan_interval",  10),
        market_open   = schedule_cfg.get("market_open",  "09:00"),
        market_close  = schedule_cfg.get("market_close", "15:20"),
    )

    trader.run()


if __name__ == "__main__":
    main()
