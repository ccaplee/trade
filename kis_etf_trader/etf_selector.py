"""
ETF 선별 모듈
장 시작 후 거래량과 가격 변동성이 큰 ETF 상위 N개를 선별합니다.
"""

from typing import Any

from .api_client import KISClient
from .config import Config
from .logger import setup_logger

logger = setup_logger(__name__)

# 국내 ETF 종목 코드 접두사 패턴 (코스피/코스닥 ETF는 일반적으로 069500 등)
# KIS API의 거래량/등락률 순위에서 ETF 여부는 'bstp_kor_isnm'(업종한글종목명) 또는
# 'mrkt_div_cls_code' 필드로 필터링합니다.
_ETF_MARKET_CODE = "ETF"


def _is_etf(item: dict[str, Any]) -> bool:
    """API 응답 항목이 ETF인지 판별합니다.

    KIS 순위 API는 종목명(hts_kor_isnm)에 ETF 관련 문자열을 포함하거나
    etf_dvsn_name 필드를 제공합니다. 두 가지 모두 체크합니다.
    """
    name: str = item.get("hts_kor_isnm", "")
    etf_flag: str = item.get("etf_dvsn_name", "")
    return bool(etf_flag) or any(
        kw in name for kw in ["ETF", "KODEX", "TIGER", "ARIRANG", "KBSTAR", "HANARO", "KOSEF", "ACE", "SOL"]
    )


def select_top_etfs(client: KISClient) -> list[str]:
    """거래량·변동성 복합 점수로 ETF 상위 N개 종목 코드를 반환합니다.

    점수 = (거래량 순위 역수 × 거래량 가중치) + (변동성 순위 역수 × 변동성 가중치)

    Returns:
        종목 코드 리스트 (최대 Config.ETF_TOP_N개)
    """
    volume_rank: list[dict[str, Any]] = []
    fluct_rank: list[dict[str, Any]] = []

    try:
        volume_rank = client.get_volume_rank()
    except Exception as exc:
        logger.warning("거래량 순위 조회 실패: %s", exc)

    try:
        fluct_rank = client.get_fluctuation_rank()
    except Exception as exc:
        logger.warning("등락률 순위 조회 실패: %s", exc)

    if not volume_rank and not fluct_rank:
        logger.error("ETF 선별 데이터를 가져오지 못했습니다.")
        return []

    # ETF만 필터링하여 {ticker: score} 딕셔너리 구축
    scores: dict[str, float] = {}

    for rank_idx, item in enumerate(volume_rank):
        if not _is_etf(item):
            continue
        ticker = item.get("mksc_shrn_iscd", "").strip()
        if not ticker:
            continue
        vol_score = (1 / (rank_idx + 1)) * Config.ETF_VOLUME_WEIGHT
        scores[ticker] = scores.get(ticker, 0.0) + vol_score

    for rank_idx, item in enumerate(fluct_rank):
        if not _is_etf(item):
            continue
        ticker = item.get("mksc_shrn_iscd", "").strip()
        if not ticker:
            continue
        fluct_score = (1 / (rank_idx + 1)) * Config.ETF_VOLATILITY_WEIGHT
        scores[ticker] = scores.get(ticker, 0.0) + fluct_score

    sorted_tickers = sorted(scores, key=lambda t: scores[t], reverse=True)
    selected = sorted_tickers[: Config.ETF_TOP_N]

    logger.info(
        "ETF 선별 완료: %s",
        ", ".join(f"{t}({scores[t]:.4f})" for t in selected),
    )
    return selected
