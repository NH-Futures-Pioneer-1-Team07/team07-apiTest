"""가짜 NH 서버를 붙인 실행기. 실제 NH는 부르지 않는다."""

import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.cases import Case
from app.catalog import load_catalog
from app.config import Settings, get_settings
from app.market import KST
from app.nh import NHClient
from app.runner import Runner

Handler = Callable[[httpx.Request, dict[str, Any] | None], httpx.Response]

# 평일 장중 (2026-11-18 수 10:00 KST)
WEEKDAY_NOON = datetime(2026, 11, 18, 10, 0, tzinfo=KST)


class FakeNH:
    def __init__(self) -> None:
        self.routes: dict[str, Handler | list[Handler]] = {}
        self.calls: list[tuple[str, dict[str, Any] | None, dict[str, str]]] = []
        self.tokens_issued = 0

    def on(self, path: str, handler: Handler | list[Handler]) -> None:
        self.routes[path] = handler

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = None
        if request.content and request.headers.get("content-type", "").startswith("application/json"):
            body = json.loads(request.content)
        self.calls.append((path, body, dict(request.headers)))
        if path == "/auth-service/v1/token":
            self.tokens_issued += 1
            return httpx.Response(200, json={"access_token": f"tok{self.tokens_issued}", "token_type": "Bearer", "scopes": "S", "expires_in": 86400, "expires_at": "2099-01-01 00:00:00"})
        h = self.routes.get(path)
        if h is None:
            return httpx.Response(404, json={"errorCode": "404", "errorMessage": "not found"})
        if isinstance(h, list):
            h = h.pop(0) if len(h) > 1 else h[0]
        return h(request, body)

    def count(self, path: str) -> int:
        return sum(1 for p, _, _ in self.calls if p == path)


def ok(data: Any) -> Handler:
    return lambda req, body: httpx.Response(200, json=data)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    base = get_settings()
    return Settings(
        nh_env="mock",
        nh_app_key=SecretStr("k"),
        nh_app_secret=SecretStr("s"),
        nh_overseas_app_key=SecretStr("ok"),
        nh_overseas_app_secret=SecretStr("os"),
        nh_docs_dir=base.nh_docs_dir,
        cases_dir=tmp_path / "cases",
        issues_dir=tmp_path / "issues",
        db_path=tmp_path / "runs.sqlite3",
    )


@pytest.fixture
def apis(settings: Settings):
    return {a.id: a for a in load_catalog(settings.nh_docs_dir)}


@pytest.fixture
def fake() -> FakeNH:
    return FakeNH()


@pytest.fixture
def make_runner(settings: Settings, apis, fake: FakeNH):
    def make(clock: datetime = WEEKDAY_NOON, **overrides: Any) -> Runner:
        s = settings.model_copy(update=overrides)
        client = NHClient(s, http=httpx.Client(transport=httpx.MockTransport(fake)), sleep=lambda _: None, slow_retry_wait_s=0)
        return Runner(s, apis, client, clock=lambda: clock, sleep=lambda _: None)

    return make


def case(data: dict[str, Any]) -> Case:
    return Case.model_validate({"id": "T", "name": "t", **data})
