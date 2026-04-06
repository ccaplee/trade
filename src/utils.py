"""
유틸리티 모듈

설정 파일 로드, 로깅 초기화 등 공통 유틸리티 기능을 제공합니다.
"""

import os
import sys
from pathlib import Path
from typing import Any
import yaml
from loguru import logger


def load_config(config_path: str = "config/config.yaml") -> dict:
    """YAML 설정 파일 로드"""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {config_path}")
    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config


def setup_logging(config: dict):
    """로거 설정"""
    log_config = config.get("logging", {})
    level = log_config.get("level", "INFO")
    log_file = log_config.get("file", "logs/trading.log")
    rotation = log_config.get("rotation", "1 day")
    retention = log_config.get("retention", "30 days")

    # 로그 디렉토리 생성
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)

    logger.remove()
    logger.add(
        sys.stdout,
        level=level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>",
        colorize=True,
    )
    logger.add(
        log_file,
        level=level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
        rotation=rotation,
        retention=retention,
        encoding="utf-8",
    )


def get_etf_list(config: dict) -> list[str]:
    """설정에서 ETF 종목 코드 목록 추출"""
    raw_list = config.get("trading", {}).get("etf_list", [])
    codes = []
    for item in raw_list:
        if isinstance(item, str):
            codes.append(item)
        elif isinstance(item, dict):
            # {"name": "code"} 형태 처리
            codes.extend(item.values())
    return codes


def validate_config(config: dict) -> bool:
    """설정 값 유효성 검사"""
    is_mock = config["kis"]["mock"]
    prefix = "mock" if is_mock else "real"

    app_key = config["kis"].get(f"{prefix}_app_key", "")
    app_secret = config["kis"].get(f"{prefix}_app_secret", "")
    account_no = config["kis"].get("account_no", "")

    errors = []
    if "YOUR_" in app_key:
        errors.append(f"kis.{prefix}_app_key를 실제 값으로 설정해주세요.")
    if "YOUR_" in app_secret:
        errors.append(f"kis.{prefix}_app_secret를 실제 값으로 설정해주세요.")
    if "X" * 6 in account_no:
        errors.append("kis.account_no를 실제 계좌번호로 설정해주세요.")

    for err in errors:
        logger.error("설정 오류: {}", err)

    return len(errors) == 0


def format_price(price: int) -> str:
    """가격 포맷 (천단위 구분)"""
    return f"{price:,}원"


def format_pnl(pnl_rate: float) -> str:
    """수익률 포맷 (색상 표시)"""
    sign = "+" if pnl_rate >= 0 else ""
    return f"{sign}{pnl_rate:.2f}%"
