"""
ETF 선정 모듈 - 거래량·변동성 기반 상위 ETF 자동 선별
"""
import logging
from datetime import datetime
from typing import Any

import kis_api
import config

logger = logging.getLogger(__name__)


_DEFAULT_RANK = 99  # 순위 정보가 없을 때 사용하는 기본값 (최하위로 취급)


def _compute_score(item: dict) -> float:
    """
    종목 점수 계산:
        score = 거래량 순위 점수(역수) * 0.5 + 등락률 절대값 * 0.5
    """
    try:
        rank = int(item.get("data_rank", str(_DEFAULT_RANK)))
        rank_score = 1.0 / rank if rank > 0 else 0.0
        chng_rate = abs(float(item.get("prdy_ctrt", "0")))
        return rank_score * 0.5 + chng_rate * 0.5
    except (ValueError, ZeroDivisionError):
        return 0.0


def _is_valid_etf(item: dict) -> bool:
    """가격 범위·ETF 조건 필터"""
    try:
        price = int(item.get("stck_prpr", item.get("prpr", "0")))
        return config.ETF_MIN_PRICE <= price <= config.ETF_MAX_PRICE
    except ValueError:
        return False


def select_top_etfs(count: int = config.ETF_SELECT_COUNT) -> list[dict[str, Any]]:
    """
    장 시작 후 거래량과 가격 변동성이 큰 ETF 상위 N개를 선별합니다.

    선별 기준:
    1. 거래량 상위 ETF 목록 수집
    2. 등락률 상위 ETF 목록 수집
    3. 두 목록을 통합 후 중복 제거
    4. 가격 범위 필터 적용
    5. 복합 점수(거래량 + 변동성) 기준 상위 N개 반환

    Returns:
        선별된 ETF 정보 리스트:
        [{"code": "069500", "name": "KODEX 200", "price": 27000,
          "change_rate": 1.2, "score": 0.83}, ...]
    """
    logger.info("ETF 선정 시작 (기준시각: %s)", datetime.now().strftime("%H:%M:%S"))

    # 거래량 상위 ETF 수집
    vol_items: list[dict] = []
    try:
        vol_items = kis_api.get_volume_rank(
            market_code="0000",
            sort_field="1",
            etf_only=True,
            count=config.ETF_VOLUME_RANK_COUNT,
        )
        logger.debug("거래량 순위 ETF %d개 수집", len(vol_items))
    except Exception as exc:
        logger.warning("거래량 순위 조회 실패: %s", exc)

    # 등락률 상위 ETF 수집 (상승)
    fluc_items: list[dict] = []
    try:
        fluc_items = kis_api.get_fluctuation_rank(
            market_code="0000",
            sort_type="1",
            count=config.ETF_VOLUME_RANK_COUNT,
        )
        logger.debug("등락률 순위 ETF %d개 수집", len(fluc_items))
    except Exception as exc:
        logger.warning("등락률 순위 조회 실패: %s", exc)

    # 종목 코드 기준 병합 (중복 제거)
    merged: dict[str, dict] = {}
    for rank, item in enumerate(vol_items, start=1):
        code = item.get("mksc_shrn_iscd", item.get("stck_shrn_iscd", ""))
        if not code:
            continue
        item["data_rank"] = str(rank)
        item["prdy_ctrt"] = item.get("prdy_ctrt", "0")
        merged[code] = item

    for rank, item in enumerate(fluc_items, start=1):
        code = item.get("mksc_shrn_iscd", item.get("stck_shrn_iscd", ""))
        if not code:
            continue
        if code not in merged:
            item["data_rank"] = str(rank + len(vol_items))
            merged[code] = item
        else:
            # 이미 있으면 등락률 업데이트
            merged[code]["prdy_ctrt"] = item.get("prdy_ctrt", merged[code].get("prdy_ctrt", "0"))

    # 가격 범위 필터
    candidates = [item for item in merged.values() if _is_valid_etf(item)]
    logger.debug("가격 필터 통과 후 %d개 후보", len(candidates))

    # 복합 점수 계산 후 정렬
    scored = sorted(candidates, key=_compute_score, reverse=True)

    result = []
    for item in scored[:count]:
        code = item.get("mksc_shrn_iscd", item.get("stck_shrn_iscd", ""))
        name = item.get("hts_kor_isnm", item.get("itms_name", code))
        price = int(item.get("stck_prpr", item.get("prpr", "0")))
        change_rate = float(item.get("prdy_ctrt", "0"))
        result.append(
            {
                "code": code,
                "name": name,
                "price": price,
                "change_rate": change_rate,
                "score": round(_compute_score(item), 4),
            }
        )
        logger.info(
            "  선정 ETF: [%s] %s  현재가=%d  등락률=%.2f%%  점수=%.4f",
            code, name, price, change_rate, result[-1]["score"],
        )

    if not result:
        logger.warning("선정된 ETF가 없습니다. 조건을 완화하거나 장 시작 후 재시도 하세요.")

    return result
