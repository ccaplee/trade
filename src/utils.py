"""
유틸리티 모듈

- 로깅 설정
- 공통 헬퍼 함수
"""
import logging
import sys
from pathlib import Path


def setup_logging(log_level: str = "INFO", log_file: str | None = None) -> None:
    """애플리케이션 로깅을 설정합니다."""
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )
    # 외부 라이브러리 로그 레벨 조정
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)


def format_price(price: int | float) -> str:
    """가격을 쉼표 포맷으로 반환합니다. 예: 1234567 → '1,234,567원'"""
    return f"{int(price):,}원"


def format_pct(pct: float) -> str:
    """등락률을 포맷합니다. 예: 1.23 → '+1.23%'"""
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.2f}%"
