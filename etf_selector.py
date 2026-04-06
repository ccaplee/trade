"""
ETF 선정 모듈
장 시작 후 거래량과 가격 변동성이 큰 ETF 상위 N개를 자동 선별합니다.

선별 방법:
1. KIS 거래량 순위 API에서 ETF 유니버스에 속한 종목을 필터링
2. 각 종목의 (거래량 비율 × 변동률) 조합 점수로 상위 N개 선택
"""

from __future__ import annotations

import logging
from typing import Any

import config
from kis_api import KISClient

logger = logging.getLogger(__name__)


def _volatility_score(item: dict[str, Any]) -> float:
    """거래량과 가격 변동성을 결합한 점수를 반환합니다."""
    try:
        volume = float(item.get("acml_vol", 0))          # 누적 거래량
        change_rate = abs(float(item.get("prdy_ctrt", 0)))  # 전일 대비 등락률(절대값)
        avg_volume = float(item.get("avrg_vol", 1) or 1)  # 거래량 평균(0 방지)
        vol_ratio = volume / avg_volume                    # 거래량 상대 비율
        return vol_ratio * (1 + change_rate / 100)
    except (ValueError, ZeroDivisionError):
        return 0.0


def select_top_etfs(client: KISClient) -> list[str]:
    """KIS 거래량 순위에서 ETF 유니버스 대상으로 상위 N개 티커를 반환합니다."""
    logger.info("ETF 선별 시작 (유니버스 크기=%d, 선택=%d)", len(config.ETF_UNIVERSE), config.TOP_N)

    universe_set = set(config.ETF_UNIVERSE)
    candidates: list[dict[str, Any]] = []

    try:
        rank_list = client.get_volume_rank()
    except Exception as exc:
        logger.warning("거래량 순위 API 오류: %s – 유니버스 전체 반환", exc)
        return config.ETF_UNIVERSE[: config.TOP_N]

    for item in rank_list:
        ticker = item.get("mksc_shrn_iscd", "")
        if ticker in universe_set:
            candidates.append(item)

    if not candidates:
        logger.warning("순위 API 결과에서 ETF 유니버스 종목을 찾지 못했습니다. 유니버스 상위 %d개 사용.", config.TOP_N)
        return config.ETF_UNIVERSE[: config.TOP_N]

    candidates.sort(key=_volatility_score, reverse=True)
    selected = [c["mksc_shrn_iscd"] for c in candidates[: config.TOP_N]]
    logger.info("선별된 ETF: %s", selected)
    return selected
