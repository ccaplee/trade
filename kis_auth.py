"""
KIS API 인증 모듈 - Access Token 발급 및 갱신 관리
"""
import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

import config

logger = logging.getLogger(__name__)

_TOKEN_CACHE_FILE = Path(".kis_token_cache.json")

_access_token: str = ""
_token_expires_at: float = 0.0


def _load_cached_token() -> bool:
    """디스크에 캐시된 토큰이 유효하면 메모리에 로드합니다."""
    global _access_token, _token_expires_at
    if not _TOKEN_CACHE_FILE.exists():
        return False
    try:
        data = json.loads(_TOKEN_CACHE_FILE.read_text())
        expires_at = float(data.get("expires_at", 0))
        if time.time() < expires_at - 60:  # 만료 1분 전까지 유효
            _access_token = data["access_token"]
            _token_expires_at = expires_at
            logger.debug("캐시에서 Access Token 로드 완료")
            return True
    except Exception as exc:
        logger.warning("토큰 캐시 읽기 실패: %s", exc)
    return False


def _save_token_cache(token: str, expires_at: float) -> None:
    """토큰과 만료 시각을 디스크에 저장합니다."""
    try:
        _TOKEN_CACHE_FILE.write_text(
            json.dumps({"access_token": token, "expires_at": expires_at})
        )
        # 소유자만 읽을 수 있도록 권한 제한
        os.chmod(_TOKEN_CACHE_FILE, 0o600)
    except Exception as exc:
        logger.warning("토큰 캐시 저장 실패: %s", exc)


def _issue_token() -> None:
    """KIS API에서 새 Access Token을 발급받습니다."""
    global _access_token, _token_expires_at
    url = f"{config.BASE_URL}/oauth2/tokenP"
    payload = {
        "grant_type": "client_credentials",
        "appkey": config.APP_KEY,
        "appsecret": config.APP_SECRET,
    }
    resp = requests.post(url, json=payload, timeout=10)
    resp.raise_for_status()
    body = resp.json()

    if "access_token" not in body:
        raise RuntimeError(f"토큰 발급 실패: {body}")

    _access_token = body["access_token"]
    # API 응답의 expires_in(초) 또는 token_type에서 만료 시각 계산
    expires_in = int(body.get("expires_in", 86400))
    _token_expires_at = time.time() + expires_in
    _save_token_cache(_access_token, _token_expires_at)
    logger.info("Access Token 발급 완료 (만료: %s)", datetime.fromtimestamp(_token_expires_at))


def get_token() -> str:
    """유효한 Access Token을 반환합니다. 필요 시 자동 갱신합니다."""
    global _access_token, _token_expires_at
    if not _access_token or time.time() >= _token_expires_at - 60:
        if not _load_cached_token():
            _issue_token()
    return _access_token


def get_headers(tr_id: str, extra: dict | None = None) -> dict:
    """KIS API 공통 요청 헤더를 생성합니다."""
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {get_token()}",
        "appkey": config.APP_KEY,
        "appsecret": config.APP_SECRET,
        "tr_id": tr_id,
        "custtype": "P",  # 개인
    }
    if extra:
        headers.update(extra)
    return headers
