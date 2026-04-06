"""
KIS ETF 단타 자동매매 진입점

실행 방법:
    cp .env.example .env        # API 키 설정
    pip install -r requirements.txt
    python main.py
"""
import argparse
import sys

from src.utils import setup_logging
from src.trader import Trader


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="한국투자증권 KIS Open API 기반 국내 ETF 단타 자동매매"
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="로그 레벨 (기본값: INFO)",
    )
    parser.add_argument(
        "--log-file",
        default=None,
        help="로그 파일 경로 (기본값: 콘솔 출력만)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    setup_logging(log_level=args.log_level, log_file=args.log_file)

    try:
        trader = Trader()
        trader.run()
    except KeyboardInterrupt:
        print("\n프로그램이 사용자에 의해 종료되었습니다.")
        sys.exit(0)
    except Exception as exc:
        print(f"오류 발생: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
