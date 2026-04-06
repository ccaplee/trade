"""
진입점 – ETF 자동매매 프로그램 실행
"""

import logging
import sys

from trader import Trader


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("trade.log", encoding="utf-8"),
        ],
    )


if __name__ == "__main__":
    _setup_logging()
    Trader().run()
