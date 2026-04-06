"""
ETF 스크리너 모듈

장 시작 후 거래량과 가격 변동성이 큰 ETF 상위 5개를 자동 선별합니다.

선별 기준:
  score = 거래량_정규화 * VOL_WEIGHT + 변동성_정규화 * VOLA_WEIGHT

ETF 판별: 종목명에 'ETF' 포함 여부 또는 종목코드가 ETF 패턴(1/2/4/5로 시작하는 6자리)을 사용.
보다 정확하게는 KIS API 종목 분류 코드(bstp_kor_isnm, bstp_cls_code)를 활용합니다.
"""
import logging
from dataclasses import dataclass, field

import pandas as pd

from .kis_api import KISApi

logger = logging.getLogger(__name__)

# 스크리닝 파라미터
VOL_WEIGHT = 0.5        # 거래량 가중치
VOLA_WEIGHT = 0.5       # 변동성 가중치
TOP_N = 5               # 선별 ETF 수
MIN_PRICE = 3_000       # 최소 현재가 (원)
MAX_PRICE = 200_000     # 최대 현재가 (원)
MIN_VOLUME = 50_000     # 최소 거래량


@dataclass
class EtfCandidate:
    """ETF 후보 종목 정보"""
    code: str
    name: str
    current_price: int
    open_price: int
    high_price: int
    low_price: int
    volume: int
    change_rate: float          # 전일 대비 등락률 (%)
    intraday_range_rate: float  # 당일 고저 범위율 (%)
    score: float = 0.0
    extra: dict = field(default_factory=dict)


class EtfScreener:
    """ETF 스크리너"""

    def __init__(self, api: KISApi):
        self.api = api

    # ------------------------------------------------------------------
    # ETF 판별
    # ------------------------------------------------------------------

    @staticmethod
    def _is_etf(item: dict) -> bool:
        """거래량 순위 항목이 ETF인지 판별합니다."""
        name: str = item.get("hts_kor_isnm", "")
        # KIS 거래량순위 API의 분류코드: bstp_cls_code = "ETF"
        cls_code: str = item.get("bstp_cls_code", "")
        return cls_code == "ETF" or "ETF" in name.upper()

    # ------------------------------------------------------------------
    # 점수 계산
    # ------------------------------------------------------------------

    @staticmethod
    def _calc_intraday_range(high: int, low: int, base_price: int) -> float:
        """당일 고저 범위율 (%)를 계산합니다."""
        if base_price <= 0:
            return 0.0
        return (high - low) / base_price * 100

    @staticmethod
    def _normalize(series: pd.Series) -> pd.Series:
        """Min-Max 정규화"""
        mn, mx = series.min(), series.max()
        if mx == mn:
            return pd.Series([0.0] * len(series), index=series.index)
        return (series - mn) / (mx - mn)

    # ------------------------------------------------------------------
    # 공개 인터페이스
    # ------------------------------------------------------------------

    def screen(self) -> list[EtfCandidate]:
        """
        거래량 상위 ETF를 조회하고 점수를 산정하여 상위 TOP_N개를 반환합니다.
        """
        logger.info("ETF 스크리닝 시작...")
        raw = self.api.get_volume_rank(fid_vol_cnt=str(MIN_VOLUME))

        candidates: list[EtfCandidate] = []
        for item in raw:
            if not self._is_etf(item):
                continue

            try:
                code = item["mksc_shrn_iscd"]
                name = item["hts_kor_isnm"]
                current_price = int(item.get("stck_prpr", "0"))
                open_price = int(item.get("stck_oprc", "0") or "0")
                high_price = int(item.get("stck_hgpr", "0") or "0")
                low_price = int(item.get("stck_lwpr", "0") or "0")
                volume = int(item.get("acml_vol", "0") or "0")
                change_rate = float(item.get("prdy_ctrt", "0") or "0")
            except (KeyError, ValueError) as exc:
                logger.debug("항목 파싱 오류 (%s): %s", item.get("mksc_shrn_iscd"), exc)
                continue

            if not (MIN_PRICE <= current_price <= MAX_PRICE):
                continue
            if volume < MIN_VOLUME:
                continue

            intraday_range = self._calc_intraday_range(
                high_price, low_price, open_price or current_price
            )

            candidates.append(
                EtfCandidate(
                    code=code,
                    name=name,
                    current_price=current_price,
                    open_price=open_price,
                    high_price=high_price,
                    low_price=low_price,
                    volume=volume,
                    change_rate=change_rate,
                    intraday_range_rate=intraday_range,
                    extra=item,
                )
            )

        if not candidates:
            logger.warning("ETF 후보가 없습니다.")
            return []

        df = pd.DataFrame(
            [
                {
                    "code": c.code,
                    "volume": c.volume,
                    "intraday_range_rate": c.intraday_range_rate,
                }
                for c in candidates
            ]
        )

        df["vol_score"] = self._normalize(df["volume"])
        df["vola_score"] = self._normalize(df["intraday_range_rate"])
        df["score"] = df["vol_score"] * VOL_WEIGHT + df["vola_score"] * VOLA_WEIGHT
        df = df.sort_values("score", ascending=False).reset_index(drop=True)

        # 점수를 후보 객체에 반영
        score_map = df.set_index("code")["score"].to_dict()
        for c in candidates:
            c.score = score_map.get(c.code, 0.0)

        # 정렬 후 TOP_N 반환
        top = sorted(candidates, key=lambda x: x.score, reverse=True)[:TOP_N]

        logger.info("선별된 ETF %d개:", len(top))
        for i, c in enumerate(top, 1):
            logger.info(
                "  %d. [%s] %s  현재가=%d  거래량=%d  변동성=%.2f%%  점수=%.4f",
                i, c.code, c.name, c.current_price, c.volume,
                c.intraday_range_rate, c.score,
            )

        return top
