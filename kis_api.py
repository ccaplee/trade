"""
kis_api.py – 한국투자증권 KIS Open API REST 연동 모듈

제공 기능:
  - OAuth2 접근토큰 발급 및 자동 갱신
  - 주식(ETF) 현재가 및 5분봉 시세 조회
  - 현금 매수 / 매도 주문
  - 잔고 및 보유 종목 조회
  - 거래량·변동성 기준 ETF 랭킹 조회
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import requests

import config

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 데이터 클래스
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TokenInfo:
    access_token: str
    expires_at: datetime


@dataclass
class Candle:
    """5분봉 캔들 1개"""
    dt: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass
class Quote:
    """현재가 스냅샷"""
    code: str
    name: str
    price: float
    change_rate: float    # 등락률 (%)
    volume: int
    ask: float
    bid: float


@dataclass
class Position:
    """보유 종목"""
    code: str
    name: str
    quantity: int
    avg_price: float
    current_price: float

    @property
    def profit_rate(self) -> float:
        if self.avg_price == 0:
            return 0.0
        return (self.current_price - self.avg_price) / self.avg_price


# ─────────────────────────────────────────────────────────────────────────────
# KIS API 클라이언트
# ─────────────────────────────────────────────────────────────────────────────

class KISClient:
    """KIS Open API REST 클라이언트"""

    def __init__(
        self,
        app_key: str = config.APP_KEY,
        app_secret: str = config.APP_SECRET,
        base_url: str = config.BASE_URL,
        cano: str = config.CANO,
        acnt_prdt_cd: str = config.ACNT_PRDT_CD,
    ) -> None:
        self.app_key = app_key
        self.app_secret = app_secret
        self.base_url = base_url.rstrip("/")
        self.cano = cano
        self.acnt_prdt_cd = acnt_prdt_cd
        self._token_info: TokenInfo | None = None
        self._session = requests.Session()

    # ── 내부 헬퍼 ────────────────────────────────────────────────────────────

    def _get_token(self) -> str:
        """접근 토큰을 반환한다. 만료 5분 전에 자동 재발급."""
        if (
            self._token_info is None
            or datetime.now() >= self._token_info.expires_at - timedelta(minutes=5)
        ):
            self._token_info = self._issue_token()
        return self._token_info.access_token

    def _issue_token(self) -> TokenInfo:
        """OAuth2 접근토큰 발급"""
        url = f"{self.base_url}/oauth2/tokenP"  # KIS API 공식 토큰 발급 엔드포인트 경로
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }
        resp = self._session.post(url, json=body, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        expires_at = datetime.now() + timedelta(seconds=int(data["expires_in"]))
        logger.info("KIS 토큰 발급 완료. 만료: %s", expires_at.strftime("%H:%M:%S"))
        return TokenInfo(access_token=data["access_token"], expires_at=expires_at)

    def _headers(self, tr_id: str, extra: dict[str, str] | None = None) -> dict[str, str]:
        h = {
            "Content-Type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self._get_token()}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }
        if extra:
            h.update(extra)
        return h

    def _get(self, path: str, tr_id: str, params: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        resp = self._session.get(
            url, headers=self._headers(tr_id), params=params, timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("rt_cd") != "0":
            raise RuntimeError(
                f"[{tr_id}] API 오류 {data.get('msg_cd')}: {data.get('msg1')}"
            )
        return data

    def _post(self, path: str, tr_id: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        resp = self._session.post(
            url, headers=self._headers(tr_id), json=body, timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("rt_cd") != "0":
            raise RuntimeError(
                f"[{tr_id}] API 오류 {data.get('msg_cd')}: {data.get('msg1')}"
            )
        return data

    # ── 시세 조회 ─────────────────────────────────────────────────────────────

    def get_quote(self, code: str) -> Quote:
        """주식(ETF) 현재가 조회"""
        data = self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-price",
            tr_id="FHKST01010100",
            params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code},
        )
        o = data["output"]
        return Quote(
            code=code,
            name=o.get("hts_kor_isnm", ""),
            price=float(o["stck_prpr"]),
            change_rate=float(o["prdy_ctrt"]),
            volume=int(o["acml_vol"]),
            ask=float(o["askp1"]),
            bid=float(o["bidp1"]),
        )

    def get_candles(self, code: str, count: int = 30) -> list[Candle]:
        """5분봉 캔들 조회 (최근 count 개, 시간 오름차순)"""
        data = self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
            tr_id="FHKST03010200",
            params={
                "FID_ETC_CLS_CODE": "",
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": code,
                "FID_INPUT_HOUR_1": datetime.now().strftime("%H%M%S"),
                "FID_PW_DATA_INCU_YN": "Y",
            },
        )
        candles: list[Candle] = []
        for item in data.get("output2", []):
            try:
                dt_str = item["stck_bsop_date"] + item["stck_cntg_hour"]
                dt = datetime.strptime(dt_str, "%Y%m%d%H%M%S")
                candles.append(
                    Candle(
                        dt=dt,
                        open=float(item["stck_oprc"]),
                        high=float(item["stck_hgpr"]),
                        low=float(item["stck_lwpr"]),
                        close=float(item["stck_prpr"]),
                        volume=int(item["cntg_vol"]),
                    )
                )
            except (KeyError, ValueError) as exc:
                logger.debug("캔들 파싱 오류: %s", exc)
        candles.sort(key=lambda c: c.dt)
        return candles[-count:] if len(candles) > count else candles

    # ── 잔고 / 보유 종목 ──────────────────────────────────────────────────────

    def get_balance(self) -> float:
        """주문 가능 현금 잔고 조회 (원)"""
        # 모의투자: VTTC8434R, 실전투자: TTTC8434R
        tr_id = "VTTC8434R" if "vts" in self.base_url else "TTTC8434R"
        data = self._get(
            "/uapi/domestic-stock/v1/trading/inquire-psbl-order",
            tr_id=tr_id,
            params={
                "CANO": self.cano,
                "ACNT_PRDT_CD": self.acnt_prdt_cd,
                "PDNO": "069500",
                "ORD_UNPR": "0",
                "ORD_DVSN": "01",
                "CMA_EVLU_AMT_ICLD_YN": "Y",
                "OVRS_ICLD_YN": "N",
            },
        )
        return float(data["output"]["ord_psbl_cash"])

    def get_positions(self) -> list[Position]:
        """보유 종목 목록 조회"""
        # 모의투자: VTTC8434R → 잔고: VTTC8908R, 실전: TTTC8908R
        tr_id = "VTTC8908R" if "vts" in self.base_url else "TTTC8908R"
        data = self._get(
            "/uapi/domestic-stock/v1/trading/inquire-balance",
            tr_id=tr_id,
            params={
                "CANO": self.cano,
                "ACNT_PRDT_CD": self.acnt_prdt_cd,
                "AFHR_FLPR_YN": "N",
                "OFL_YN": "",
                "INQR_DVSN": "02",
                "UNPR_DVSN": "01",
                "FUND_STTL_ICLD_YN": "N",
                "FNCG_AMT_AUTO_RDPT_YN": "N",
                "PRCS_DVSN": "01",
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": "",
            },
        )
        positions = []
        for item in data.get("output1", []):
            qty = int(item.get("hldg_qty", "0"))
            if qty <= 0:
                continue
            positions.append(
                Position(
                    code=item["pdno"],
                    name=item.get("prdt_name", ""),
                    quantity=qty,
                    avg_price=float(item.get("pchs_avg_pric", "0")),
                    current_price=float(item.get("prpr", "0")),
                )
            )
        return positions

    # ── 주문 ──────────────────────────────────────────────────────────────────

    def buy_market(self, code: str, quantity: int) -> str:
        """시장가 매수. 주문번호 반환."""
        # 모의투자: VTTC0802U, 실전: TTTC0802U
        tr_id = "VTTC0802U" if "vts" in self.base_url else "TTTC0802U"
        data = self._post(
            "/uapi/domestic-stock/v1/trading/order-cash",
            tr_id=tr_id,
            body={
                "CANO": self.cano,
                "ACNT_PRDT_CD": self.acnt_prdt_cd,
                "PDNO": code,
                "ORD_DVSN": "01",   # 시장가
                "ORD_QTY": str(quantity),
                "ORD_UNPR": "0",
            },
        )
        order_no = data["output"]["ODNO"]
        logger.info("매수 주문 완료 [%s] %d주, 주문번호: %s", code, quantity, order_no)
        return order_no

    def sell_market(self, code: str, quantity: int) -> str:
        """시장가 매도. 주문번호 반환."""
        # 모의투자: VTTC0801U, 실전: TTTC0801U
        tr_id = "VTTC0801U" if "vts" in self.base_url else "TTTC0801U"
        data = self._post(
            "/uapi/domestic-stock/v1/trading/order-cash",
            tr_id=tr_id,
            body={
                "CANO": self.cano,
                "ACNT_PRDT_CD": self.acnt_prdt_cd,
                "PDNO": code,
                "ORD_DVSN": "01",   # 시장가
                "ORD_QTY": str(quantity),
                "ORD_UNPR": "0",
            },
        )
        order_no = data["output"]["ODNO"]
        logger.info("매도 주문 완료 [%s] %d주, 주문번호: %s", code, quantity, order_no)
        return order_no

    # ── ETF 랭킹 ──────────────────────────────────────────────────────────────

    def get_etf_ranking(self, etf_codes: list[str]) -> list[tuple[str, float]]:
        """
        거래량 × 변동성(고가-저가/시가) 점수를 계산하여
        내림차순으로 정렬한 (code, score) 리스트를 반환한다.

        각 ETF 에 대해 현재가 API 를 호출하므로 호출 빈도에 주의하세요.
        """
        scored: list[tuple[str, float]] = []
        for code in etf_codes:
            try:
                quote = self.get_quote(code)
                candles = self.get_candles(code, count=10)
                if len(candles) >= 2:
                    recent = candles[-1]
                    volatility = (
                        (recent.high - recent.low) / recent.open
                        if recent.open > 0
                        else 0.0
                    )
                else:
                    volatility = abs(quote.change_rate) / 100.0
                score = quote.volume * volatility
                scored.append((code, score))
                time.sleep(0.05)   # API 호출 간격 (Rate Limit 방지)
            except Exception as exc:
                logger.warning("ETF 랭킹 조회 오류 [%s]: %s", code, exc)
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored
