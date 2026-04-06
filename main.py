"""
KIS ETF 자동매매 프로그램 진입점
"""

import sys

from kis_etf_trader.config import Config
from kis_etf_trader.logger import setup_logger
from kis_etf_trader.trader import Trader

logger = setup_logger("main")


def _validate_config() -> bool:
    missing = []
    if not Config.APP_KEY or Config.APP_KEY == "your_app_key_here":
        missing.append("APP_KEY")
    if not Config.APP_SECRET or Config.APP_SECRET == "your_app_secret_here":
        missing.append("APP_SECRET")
    if not Config.CANO or Config.CANO == "your_account_number_here":
        missing.append("CANO")
    if missing:
        logger.error("필수 환경변수가 설정되지 않았습니다: %s", ", ".join(missing))
        logger.error(".env 파일을 .env.example 을 참고하여 작성해 주세요.")
        return False
    return True


def main() -> None:
    if not _validate_config():
        sys.exit(1)

    trader = Trader()
    try:
        trader.run()
    except KeyboardInterrupt:
        logger.info("사용자 종료 요청 — 프로그램을 종료합니다.")
    except Exception as exc:
        logger.exception("예기치 못한 오류 발생: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
