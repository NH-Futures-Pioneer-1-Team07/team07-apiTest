"""NH선물 API 호출. 요청·응답 원문을 그대로 남기고, 판정은 하지 않는다.

- 접근토큰은 국내·해외 키별로 메모리에 보관한다. 로그와 기록에는 가려서 남긴다.
- 호출 제한(주문 5건/초, 계좌·시세 10건/초)을 지킨다.
- 다시 보내는 경우는 정해져 있다.
  - 토큰이 거부됨(401, EGW052 등): 토큰을 다시 받아 한 번 더 보낸다. 요청이 처리되지 않았다.
  - 조회가 504 EGW032(백엔드 응답 시간 초과): 10초 뒤 한 번 더 (NH-008 답변)
  - 조회가 EGW036(호출 속도 제한): 간격을 늘려 최대 3번
  - 주문·정정·취소는 다시 보내지 않는다. 같은 주문이 두 번 들어갈 수 있다 (NH-009 답변)
"""

import json
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import httpx

from app.catalog import Api, LimitKind
from app.config import Settings
from app.market import KST

TOKEN_PATH = "/auth-service/v1/token"
REISSUE_CODES = {"EG041", "EG042", "EG043", "EG044", "EG045", "EG047", "EG049", "EGW052"}
SLOW_BACKEND = "EGW032"
RATE_LIMITED = "EGW036"
PER_SECOND: dict[LimitKind, int] = {"order": 5, "account": 10, "quote": 10, "default": 10, "realtime": 10}
SECRET_KEYS = {"access_token", "appkey", "appsecret", "access_key"}


class ConfigMissing(Exception):
    """키가 설정되어 있지 않다."""


class AuthFailed(Exception):
    """토큰 발급이 거부되었다."""


@dataclass
class Exchange:
    """요청 한 번과 그 응답. 비밀값은 가려 둔다."""

    method: str
    url: str
    request_headers: dict[str, str]
    request_body: str
    status: int | None = None
    response_headers: dict[str, str] = field(default_factory=dict)
    response_text: str = ""
    body: Any = None  # JSON이면 파싱한 값 (가리기 전 원본)
    duration_ms: int = 0
    error: str | None = None  # 응답을 받지 못한 이유
    timed_out: bool = False
    note: str | None = None

    @property
    def error_code(self) -> str:
        return str(self.body.get("errorCode") or "").strip() if isinstance(self.body, dict) else ""


def mask(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k in SECRET_KEYS and isinstance(v, str) and v:
                out[k] = v[:4] + "••••••"
            elif k.endswith("ac_no") and isinstance(v, str) and len(v) > 4:
                out[k] = v[:3] + "•" * (len(v) - 5) + v[-2:]
            else:
                out[k] = mask(v)
        return out
    if isinstance(value, list):
        return [mask(v) for v in value]
    return value


def _mask_text(text: str, body: Any) -> str:
    if body is None:
        return text
    return json.dumps(mask(body), ensure_ascii=False, indent=2)


class RateLimiter:
    def __init__(self, monotonic: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep):
        self._monotonic = monotonic
        self._sleep = sleep
        self._lock = threading.Lock()
        self._next: dict[LimitKind, float] = {}

    def wait(self, kind: LimitKind) -> None:
        interval = 1.0 / PER_SECOND[kind]
        with self._lock:
            now = self._monotonic()
            at = self._next.get(kind, now)
            delay = max(0.0, at - now)
            self._next[kind] = max(at, now) + interval
        if delay > 0:
            self._sleep(delay)


class NHClient:
    def __init__(
        self,
        settings: Settings,
        http: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        slow_retry_wait_s: float = 10.0,
    ):
        self.settings = settings
        self.base_url = settings.base_url
        self._http = http or httpx.Client()
        self._sleep = sleep
        self._limiter = RateLimiter(sleep=sleep)
        self._slow_retry_wait_s = slow_retry_wait_s
        self._lock = threading.Lock()
        self._tokens: dict[str, tuple[str, datetime]] = {}

    # ---------- 토큰 ----------

    def _keys(self, market: str) -> tuple[str, str]:
        s = self.settings
        key, secret, names = (
            (s.nh_overseas_app_key, s.nh_overseas_app_secret, "NH_OVERSEAS_APP_KEY, NH_OVERSEAS_APP_SECRET")
            if market == "overseas"
            else (s.nh_app_key, s.nh_app_secret, "NH_APP_KEY, NH_APP_SECRET")
        )
        if not key or not secret or not key.get_secret_value() or not secret.get_secret_value():
            raise ConfigMissing(f"{names} 를 backend/.env 에 설정하세요")
        return key.get_secret_value(), secret.get_secret_value()

    def request_token(self, market: str = "domestic", timeout_s: float = 30.0) -> Exchange:
        """토큰 발급 요청 한 번. 토큰 발급 API 자체를 테스트할 때도 쓴다."""
        key, secret = self._keys(market)
        form = {"grant_type": "client_credentials", "appkey": key, "appsecret": secret}
        masked_form = "&".join(f"{k}={mask({k: v})[k]}" for k, v in form.items())
        ex = Exchange(
            method="POST",
            url=f"{self.base_url}{TOKEN_PATH}",
            request_headers={"Content-Type": "application/x-www-form-urlencoded"},
            request_body=masked_form,
        )
        self._limiter.wait("default")
        self._do(ex, lambda: self._http.post(ex.url, data=form, timeout=timeout_s))
        if isinstance(ex.body, dict) and ex.body.get("access_token"):
            with self._lock:
                self._tokens[market] = (str(ex.body["access_token"]), _expires_at(ex.body))
        return ex

    def token(self, market: str) -> str:
        with self._lock:
            cached = self._tokens.get(market)
        if cached and datetime.now(KST) + timedelta(minutes=5) < cached[1]:
            return cached[0]
        ex = self.request_token(market)
        if ex.error:
            raise ConnectionError(ex.error)
        with self._lock:
            cached = self._tokens.get(market)
        if not cached:
            raise AuthFailed(f"접근토큰 발급이 거부되었습니다 (HTTP {ex.status} {ex.error_code})".strip())
        return cached[0]

    def forget_token(self, market: str) -> None:
        with self._lock:
            self._tokens.pop(market, None)

    # ---------- 호출 ----------

    def send(self, api: Api, body: dict[str, Any], timeout_s: float = 30.0, auth: bool = True) -> list[Exchange]:
        """정해진 규칙대로 다시 보내는 것까지 포함해, 보낸 요청을 모두 돌려준다. 마지막이 최종 결과다."""
        attempts: list[Exchange] = []
        reissued = False
        rate_retries = 0
        slow_retried = False
        while True:
            ex = self._send_once(api, body, timeout_s, auth)
            attempts.append(ex)
            if ex.error:
                return attempts
            code = ex.error_code
            if auth and not reissued and (ex.status == 401 or code in REISSUE_CODES):
                reissued = True
                self.forget_token(api.market)
                ex.note = f"토큰 거부({code or ex.status}) → 토큰을 다시 받아 한 번 더 보냄"
                continue
            if api.is_order:
                return attempts
            if code == SLOW_BACKEND and not slow_retried:
                slow_retried = True
                ex.note = f"{ex.status} {code} → {self._slow_retry_wait_s:.0f}초 뒤 다시 보냄 (NH-008)"
                self._sleep(self._slow_retry_wait_s)
                continue
            if code == RATE_LIMITED and rate_retries < 3:
                rate_retries += 1
                ex.note = f"{code} 호출 속도 제한 → {rate_retries}초 뒤 다시 보냄"
                self._sleep(float(rate_retries))
                continue
            return attempts

    def _send_once(self, api: Api, body: dict[str, Any], timeout_s: float, auth: bool) -> Exchange:
        headers = {"Content-Type": "application/json"}
        shown = dict(headers)
        if auth:
            tok = self.token(api.market)
            headers["Authorization"] = f"Bearer {tok}"
            shown["Authorization"] = f"Bearer {tok[:4]}••••••"
        ex = Exchange(
            method=api.method or "POST",
            url=f"{self.base_url}{api.url}",
            request_headers=shown,
            request_body=json.dumps(body, ensure_ascii=False, indent=2),
        )
        self._limiter.wait(api.limitKind)
        method = (api.method or "POST").upper()
        if method == "GET":
            call = lambda: self._http.get(ex.url, headers=headers, timeout=timeout_s)  # noqa: E731
        else:
            call = lambda: self._http.post(ex.url, headers=headers, json=body, timeout=timeout_s)  # noqa: E731
        self._do(ex, call)
        return ex

    def _do(self, ex: Exchange, call: Callable[[], httpx.Response]) -> None:
        start = time.monotonic()
        try:
            r = call()
        except httpx.TimeoutException:
            ex.timed_out = True
            ex.error = "제한 시간 안에 응답이 없음"
        except httpx.HTTPError as e:
            ex.error = f"연결 실패: {type(e).__name__}"
        ex.duration_ms = int((time.monotonic() - start) * 1000)
        if ex.error:
            return
        ex.status = r.status_code
        ex.response_headers = {k: v for k, v in r.headers.items() if k.lower() in ("content-type", "content-length", "date")}
        try:
            ex.body = r.json()
        except ValueError:
            ex.body = None
        ex.response_text = _mask_text(r.text, ex.body)


def _expires_at(body: dict[str, Any]) -> datetime:
    raw = str(body.get("expires_at") or "").strip()
    if raw:
        try:
            return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)
        except ValueError:
            pass
    try:
        return datetime.now(KST) + timedelta(seconds=int(float(body.get("expires_in") or 600)))
    except (TypeError, ValueError):
        return datetime.now(KST) + timedelta(minutes=10)
