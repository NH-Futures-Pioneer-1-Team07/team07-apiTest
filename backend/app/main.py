"""화면용 HTTP API.

uv run uvicorn app.main:create_app --factory --reload
"""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import get_settings
from app.issues import ReportStatus
from app.service import Service


class RunRequest(BaseModel):
    caseIds: list[str]


class IssuePatch(BaseModel):
    reportStatus: ReportStatus


class IssueCreate(BaseModel):
    runId: str


def create_app(service: Service | None = None) -> FastAPI:
    svc = service or Service(get_settings())
    app = FastAPI(title="API 테스트 콘솔")
    app.state.service = svc

    @app.get("/api/status")
    def status() -> dict[str, Any]:
        return svc.status()

    @app.get("/api/apis")
    def apis() -> list[dict[str, Any]]:
        return [a.model_dump() for a in svc.apis]

    @app.get("/api/cases")
    def cases() -> list[dict[str, Any]]:
        return svc.cases_api()

    @app.get("/api/runs")
    def runs(limit: int = 3000) -> list[dict[str, Any]]:
        # 목록에는 최근 실행만 단계 원문을 싣는다. 나머지는 /api/runs/{id} 로 받는다
        latest = svc.store.latest_ids()
        out = svc.store.list(limit)
        for r in out:
            if r["id"] not in latest:
                r["steps"] = []
                r["stepsOmitted"] = True
        return out

    @app.get("/api/runs/{run_id}")
    def run(run_id: str) -> dict[str, Any]:
        r = svc.store.get(run_id)
        if r is None:
            raise HTTPException(404, "실행 기록이 없습니다")
        return r

    @app.post("/api/runs", status_code=202)
    def start(req: RunRequest) -> dict[str, Any]:
        try:
            return {"runIds": svc.enqueue(req.caseIds)}
        except KeyError as e:
            raise HTTPException(404, f"없는 케이스: {e}") from None

    @app.get("/api/issues")
    def issues() -> list[dict[str, Any]]:
        return [i.to_api() for i in svc.issues.list()]

    @app.patch("/api/issues/{issue_id}")
    def patch_issue(issue_id: str, req: IssuePatch) -> dict[str, Any]:
        try:
            issue = svc.issues.set_status(issue_id, req.reportStatus).to_api()
        except KeyError:
            raise HTTPException(404, "제보가 없습니다") from None
        svc.events.publish("issue", issue)
        return issue

    @app.post("/api/issues", status_code=201)
    def create_issue(req: IssueCreate) -> dict[str, Any]:
        try:
            return svc.register_issue(req.runId)
        except KeyError:
            raise HTTPException(404, "실행 기록이 없습니다") from None

    @app.get("/api/events")
    async def events() -> StreamingResponse:
        async def stream() -> AsyncIterator[str]:
            q = svc.events.subscribe()
            try:
                yield ": connected\n\n"
                while True:
                    try:
                        yield await asyncio.wait_for(q.get(), timeout=15)
                    except TimeoutError:
                        yield ": ping\n\n"
            finally:
                svc.events.unsubscribe(q)

        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    return app
