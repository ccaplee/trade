"""
한국투자증권 KIS Open API 클라이언트
- OAuth2 접근토큰 발급/갱신
- 시세 조회
- 잔고 조회
- 주문(매수/매도)
"""
import time
import logging
import requests

import config

logger = logging.getLogger(__name__)


class KISClient:
    """KIS REST API 클라이언트"""

    def __init__(self):
        self._access_token: str = ""
        self._token_expires_at: float = 0.0
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    # ── 인증 ──────────────────────────────────────────────────────────────────

    def _issue_token(self) -> None:
        """OAuth2 접근토큰 발급"""
        url = f"{config.BASE_URL}/oauth2/tokenP"
        body = {
            "grant_type": "client_credentials",
            "appkey": config.APP_KEY,
            "appsecret": config.APP_SECRET,
        }
        resp = self.session.post(url, json=body, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        self._access_token = data["access_token"]
        # 만료 1분 전 갱신
        self._token_expires_at = time.time() + int(data.get("expires_in", 86400)) - 60
        logger.info("KIS 접근토큰 발급 완료 (만료: %d초 후)", int(data.get("expires_in", 86400)) - 60)

    def _ensure_token(self) -> None:
        if not self._access_token or time.time() >= self._token_expires_at:
            self._issue_token()

    def _auth_headers(self, tr_id: str) -> dict:
        self._ensure_token()
        return {
            "authorization": f"Bearer {self._access_token}",
            "appkey": config.APP_KEY,
            "appsecret": config.APP_SECRET,
            "tr_id": tr_id,
        }

    # ── 시세 조회 ──────────────────────────────────────────────────────────────

    def get_price(self, symbol: str) -> dict:
        """
        국내 주식(ETF) 현재가 조회
        반환 dict 주요 키:
          stck_prpr  - 현재가
          prdy_ctrt  - 전일 대비율(%)
          acml_vol   - 누적 거래량
          acml_tr_pbmn - 누적 거래대금
        """
        url = f"{config.BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price"
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": symbol,
        }
        resp = self.session.get(
            url,
            headers=self._auth_headers("FHKST01010100"),
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("rt_cd") != "0":
            raise RuntimeError(f"시세 조회 오류 [{symbol}]: {data.get('msg1')}")
        return data["output"]

    def get_daily_ohlcv(self, symbol: str, count: int = 30) -> list[dict]:
        """
        국내 주식 일봉 데이터 조회 (최근 count일)
        반환: [{"stck_bsop_date", "stck_clpr", "stck_oprc", "stck_hgpr", "stck_lwpr", "acml_vol"}, ...]
        """
        url = f"{config.BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-daily-price"
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": symbol,
            "FID_PERIOD_DIV_CODE": "D",
            "FID_ORG_ADJ_PRC": "0",
        }
        resp = self.session.get(
            url,
            headers=self._auth_headers("FHKST01010400"),
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("rt_cd") != "0":
            raise RuntimeError(f"일봉 조회 오류 [{symbol}]: {data.get('msg1')}")
        return data.get("output2", [])[:count]

    # ── 잔고 / 매수가능금액 조회 ───────────────────────────────────────────────

    def get_balance(self) -> dict:
        """
        주식 잔고 조회
        반환 dict:
          holdings: [{pdno, prdt_name, hldg_qty, avg_unpr3, evlu_pfls_rt}, ...]
          cash: 예수금 총액
        """
        url = f"{config.BASE_URL}/uapi/domestic-stock/v1/trading/inquire-balance"
        params = {
            "CANO": config.ACCOUNT_NUMBER,
            "ACNT_PRDT_CD": config.ACCOUNT_PRODUCT_CODE,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "01",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }
        resp = self.session.get(
            url,
            headers=self._auth_headers(f"{config.TR_PREFIX}TTST0802R"),
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("rt_cd") != "0":
            raise RuntimeError(f"잔고 조회 오류: {data.get('msg1')}")

        holdings = data.get("output1", [])
        summary = data.get("output2", [{}])
        cash = int(summary[0].get("dnca_tot_amt", "0")) if summary else 0
        return {"holdings": holdings, "cash": cash}

    def get_buyable_amount(self, symbol: str, price: int) -> int:
        """특정 종목 매수 가능 금액(원) 조회"""
        url = f"{config.BASE_URL}/uapi/domestic-stock/v1/trading/inquire-psbl-order"
        params = {
            "CANO": config.ACCOUNT_NUMBER,
            "ACNT_PRDT_CD": config.ACCOUNT_PRODUCT_CODE,
            "PDNO": symbol,
            "ORD_UNPR": str(price),
            "ORD_DVSN": "01",
            "CMA_EVLU_AMT_ICLD_YN": "Y",
            "OVRS_ICLD_YN": "N",
        }
        resp = self.session.get(
            url,
            headers=self._auth_headers(f"{config.TR_PREFIX}TSTS0303R"),
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("rt_cd") != "0":
            raise RuntimeError(f"매수가능금액 조회 오류 [{symbol}]: {data.get('msg1')}")
        return int(data["output"].get("ord_psbl_cash", "0"))

    # ── 주문 ──────────────────────────────────────────────────────────────────

    def _place_order(
        self,
        symbol: str,
        side: str,         # "buy" or "sell"
        quantity: int,
        price: int = 0,    # 0 이면 시장가
    ) -> dict:
        """
        현금 주문 실행
        side: "buy" → 매수, "sell" → 매도
        price=0 → 시장가, price>0 → 지정가
        """
        url = f"{config.BASE_URL}/uapi/domestic-stock/v1/trading/order-cash"

        if side == "buy":
            tr_id = f"{config.TR_PREFIX}TTTC0802U"
        else:
            tr_id = f"{config.TR_PREFIX}TTTC0801U"

        ord_dvsn = "01" if price == 0 else "00"   # 01: 시장가, 00: 지정가
        body = {
            "CANO": config.ACCOUNT_NUMBER,
            "ACNT_PRDT_CD": config.ACCOUNT_PRODUCT_CODE,
            "PDNO": symbol,
            "ORD_DVSN": ord_dvsn,
            "ORD_QTY": str(quantity),
            "ORD_UNPR": str(price),
        }
        resp = self.session.post(
            url,
            headers=self._auth_headers(tr_id),
            json=body,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("rt_cd") != "0":
            raise RuntimeError(
                f"주문 오류 [{symbol} {side} {quantity}주]: {data.get('msg1')}"
            )
        logger.info(
            "[주문완료] %s %s %d주 (가격:%d) → 주문번호: %s",
            symbol, side.upper(), quantity, price,
            data.get("output", {}).get("KRX_FWDG_ORD_ORGNO", "-"),
        )
        return data["output"]

    def buy(self, symbol: str, quantity: int, price: int = 0) -> dict:
        """시장가 또는 지정가 매수"""
        return self._place_order(symbol, "buy", quantity, price)

    def sell(self, symbol: str, quantity: int, price: int = 0) -> dict:
        """시장가 또는 지정가 매도"""
        return self._place_order(symbol, "sell", quantity, price)
