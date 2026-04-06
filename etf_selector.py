"""
ETF 선별 모듈
장 시작 후 거래량과 가격 변동성이 큰 ETF 상위 N개를 자동 선별합니다.
"""
import logging
from typing import Any

import kis_api
import config

logger = logging.getLogger(__name__)

# KIS 등락률 순위 API에서 반환되는 종목 유형 코드
_ETF_MKT_CODES = {"ETF"}


def _is_etf(item: dict[str, Any]) -> bool:
    """종목명에 'ETF' 포함 여부 또는 6자리 숫자 코드로 ETF를 식별합니다."""
    name: str = item.get("hts_kor_isnm", "")
    ticker: str = item.get("mksc_shrn_iscd", "")
    return "ETF" in name.upper() or (ticker.isdigit() and len(ticker) == 6)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def select_top_etfs() -> list[str]:
    """
    거래량 순위와 등락률 순위를 결합하여 상위 ETF 종목코드 목록을 반환합니다.

    Returns
    -------
    list[str]
        상위 N개 ETF 종목코드 (config.ETF_CANDIDATE_COUNT)
    """
    vol_rank: list[dict[str, Any]] = []
    flu_rank: list[dict[str, Any]] = []

    try:
        vol_rank = kis_api.get_volume_rank()
    except Exception as exc:
        logger.warning("거래량 순위 조회 실패: %s", exc)

    try:
        flu_rank = kis_api.get_fluctuation_rank()
    except Exception as exc:
        logger.warning("등락률 순위 조회 실패: %s", exc)

    scores: dict[str, float] = {}

    # 거래량 순위 점수 부여 (1위 = 100점, 순위마다 -1점)
    for rank, item in enumerate(vol_rank[:50], start=1):
        ticker = item.get("mksc_shrn_iscd", "")
        if not ticker or not _is_etf(item):
            continue
        vol = _safe_float(item.get("acml_vol"))
        score = max(0.0, 100.0 - rank) + vol / 1_000_000  # 거래량 보너스
        scores[ticker] = scores.get(ticker, 0.0) + score

    # 등락률 순위 점수 부여 (절대 등락률 기준)
    for rank, item in enumerate(flu_rank[:50], start=1):
        ticker = item.get("mksc_shrn_iscd", "")
        if not ticker or not _is_etf(item):
            continue
        pct = abs(_safe_float(item.get("prdy_ctrt")))  # 전일 대비 등락률
        score = max(0.0, 100.0 - rank) + pct * 5
        scores[ticker] = scores.get(ticker, 0.0) + score

    sorted_tickers = sorted(scores, key=lambda t: scores[t], reverse=True)
    selected = sorted_tickers[: config.ETF_CANDIDATE_COUNT]

    logger.info("선별된 ETF (%d개): %s", len(selected), selected)
    return selected
