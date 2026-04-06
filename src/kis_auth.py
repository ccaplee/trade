"""
KIS Open API OAuth2 인증 모듈

실전투자: https://openapi.koreainvestment.com:9443
모의투자: https://openapivts.koreainvestment.com:29443
"""
import os
import json
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# API Base URL
REAL_BASE_URL = "https://openapi.koreainvestment.com:9443"
MOCK_BASE_URL = "https://openapivts.koreainvestment.com:29443"

TOKEN_CACHE_FILE = Path(".token_cache.json")


class KISAuth:
    """KIS API 인증 및 토큰 관리 클래스"""

    def __init__(self):
        self.app_key = os.environ["KIS_APP_KEY"]
        self.app_secret = os.environ["KIS_APP_SECRET"]
        self.account_no = os.environ["KIS_ACCOUNT_NO"]
        self.is_real = os.environ.get("KIS_IS_REAL", "false").lower() == "true"

        self.base_url = REAL_BASE_URL if self.is_real else MOCK_BASE_URL
        self._access_token: str | None = None
        self._token_expires_at: datetime | None = None

        # 계좌번호 분리 (예: "50123456-01" → cano="50123456", acnt_prdt_cd="01")
        parts = self.account_no.replace("-", "")
        self.cano = parts[:8]
        self.acnt_prdt_cd = parts[8:] if len(parts) > 8 else "01"

    # ------------------------------------------------------------------
    # 토큰 발급 / 캐시
    # ------------------------------------------------------------------

    def _load_cached_token(self) -> bool:
        """파일 캐시에서 유효한 토큰을 로드합니다."""
        if not TOKEN_CACHE_FILE.exists():
            return False
        try:
            data = json.loads(TOKEN_CACHE_FILE.read_text())
            expires_at = datetime.fromisoformat(data["expires_at"])
            if datetime.now() < expires_at - timedelta(minutes=5):
                self._access_token = data["access_token"]
                self._token_expires_at = expires_at
                logger.debug("캐시된 토큰 로드 성공 (만료: %s)", expires_at)
                return True
        except Exception as exc:
            logger.warning("토큰 캐시 로드 실패: %s", exc)
        return False

    def _save_token_cache(self, token: str, expires_at: datetime) -> None:
        TOKEN_CACHE_FILE.write_text(
            json.dumps({"access_token": token, "expires_at": expires_at.isoformat()})
        )

    def issue_token(self) -> str:
        """액세스 토큰을 발급합니다 (캐시 우선)."""
        if self._access_token and self._token_expires_at:
            if datetime.now() < self._token_expires_at - timedelta(minutes=5):
                return self._access_token

        if self._load_cached_token():
            return self._access_token  # type: ignore[return-value]

        url = f"{self.base_url}/oauth2/tokenP"
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        self._access_token = data["access_token"]
        expires_in = int(data.get("expires_in", 86400))
        self._token_expires_at = datetime.now() + timedelta(seconds=expires_in)
        self._save_token_cache(self._access_token, self._token_expires_at)
        logger.info("신규 토큰 발급 완료 (만료: %s)", self._token_expires_at)
        return self._access_token

    def revoke_token(self) -> None:
        """액세스 토큰을 폐기합니다."""
        if not self._access_token:
            return
        url = f"{self.base_url}/oauth2/revokeP"
        payload = {
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "token": self._access_token,
        }
        try:
            requests.post(url, json=payload, timeout=10)
            logger.info("토큰 폐기 완료")
        except Exception as exc:
            logger.warning("토큰 폐기 실패: %s", exc)
        finally:
            self._access_token = None
            self._token_expires_at = None
            TOKEN_CACHE_FILE.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # 공통 헤더
    # ------------------------------------------------------------------

    def get_headers(self, tr_id: str, custtype: str = "P") -> dict:
        """API 공통 요청 헤더를 반환합니다."""
        return {
            "Content-Type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self.issue_token()}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
            "custtype": custtype,
        }
