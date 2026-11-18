"""화면과 CLI가 함께 쓰는 서비스. 케이스는 파일에서 매번 다시 읽어서, Claude가 고친 케이스가 바로 반영된다.

실행은 작업자 스레드 하나가 줄 세워서 처리한다. 호출 제한을 지키고 주문이 겹치지 않게 하려는 것이다.
"""

import asyncio
import json
import queue
import threading
from collections.abc import Callable
from typing import Any

from app.cases import Case, load_cases, validate_case
from app.catalog import Api, load_catalog
from app.config import Settings
from app.issues import IssueStore
from app.nh import NHClient
from app.runner import Runner
from app.store import RunStore


class Broadcaster:
    """실행 상태가 바뀔 때 화면(SSE 구독자)에 알린다."""

    def __init__(self) -> None:
        self._subs: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue[str]]] = []
        self._lock = threading.Lock()

    def subscribe(self) -> asyncio.Queue[str]:
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=1000)
        with self._lock:
            self._subs.append((asyncio.get_running_loop(), q))
        return q

    def unsubscribe(self, q: asyncio.Queue[str]) -> None:
        with self._lock:
            self._subs = [(l, s) for l, s in self._subs if s is not q]

    def publish(self, event: str, data: Any) -> None:
        payload = f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        with self._lock:
            subs = list(self._subs)
        for loop, q in subs:
            try:
                loop.call_soon_threadsafe(q.put_nowait, payload)
            except RuntimeError:
                pass


class Service:
    def __init__(self, settings: Settings, client: NHClient | None = None, store: RunStore | None = None):
        self.settings = settings
        self.apis: list[Api] = load_catalog(settings.nh_docs_dir)
        self.api_by_id = {a.id: a for a in self.apis}
        self.client = client or NHClient(settings)
        self.runner = Runner(settings, self.api_by_id, self.client)
        self.store = store or RunStore(settings.db_path)
        self.issues = IssueStore(settings.issues_dir)
        self.events = Broadcaster()
        self._queue: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue()
        self._worker: threading.Thread | None = None

    # ---------- 케이스 ----------

    def load(self) -> tuple[list[Case], list[dict[str, Any]]]:
        cases, file_errors = load_cases(self.settings.cases_dir)
        problems = [{"file": e.path.name, "problems": e.problems} for e in file_errors]
        for c in cases:
            p = validate_case(c, self.api_by_id)
            if p:
                problems.append({"file": c.path.rsplit("/", 1)[-1], "caseId": c.id, "problems": p})
        return cases, problems

    def case_issue_map(self, cases: list[Case]) -> dict[str, str]:
        """케이스 → 재확인하는 제보. 케이스 파일의 issue 와 제보 파일의 cases 를 합친다."""
        m = {c.id: c.issue for c in cases if c.issue}
        for i in self.issues.list():
            for cid in i.cases:
                m.setdefault(cid, i.id)
        return m

    def cases_api(self) -> list[dict[str, Any]]:
        cases, _ = self.load()
        links = self.case_issue_map(cases)
        return [
            {
                "id": c.id,
                "name": c.name,
                "kind": c.kind(),
                "apiIds": c.api_ids(),
                "tags": c.tags,
                "issueId": links.get(c.id),
                "description": c.description,
                "when": c.when,
                "file": c.path.rsplit("/", 1)[-1],
            }
            for c in cases
        ]

    # ---------- 실행 ----------

    def enqueue(self, case_ids: list[str]) -> list[str]:
        cases, _ = self.load()
        by_id = {c.id: c for c in cases}
        unknown = [i for i in case_ids if i not in by_id]
        if unknown:
            raise KeyError(", ".join(unknown))
        run_ids = []
        for cid in case_ids:
            run = self.runner.new_run(by_id[cid])
            self.store.save(run)
            self.events.publish("run", run)
            self._queue.put((cid, run))
            run_ids.append(run["id"])
        self._ensure_worker()
        return run_ids

    def _ensure_worker(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._worker = threading.Thread(target=self._work, name="runner", daemon=True)
        self._worker.start()

    def _work(self) -> None:
        while True:
            try:
                cid, run = self._queue.get(timeout=5)
            except queue.Empty:
                return
            try:
                self.run_now(cid, run)
            except Exception as e:  # 실행기 버그로 작업자가 죽지 않게 한다
                run.update(status="error", errorKind="연결 실패", errorReason=f"실행 중 예외: {type(e).__name__}: {e}")
                self.store.save(run)
                self.events.publish("run", run)

    def run_now(self, case_id: str, run: dict[str, Any] | None = None, progress: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
        cases, _ = self.load()
        case = next(c for c in cases if c.id == case_id)
        issue_id = self.case_issue_map(cases).get(case_id)

        def on_progress(r: dict[str, Any]) -> None:
            self.store.save(r)
            self.events.publish("run", r)
            if progress:
                progress(r)

        result = self.runner.run(case, issue_id=issue_id, run=run, progress=on_progress)
        self.store.save(result)
        self.events.publish("run", result)
        return result

    # ---------- 제보 ----------

    def register_issue(self, run_id: str) -> dict[str, Any]:
        run = self.store.get(run_id)
        if run is None:
            raise KeyError(run_id)
        cases, _ = self.load()
        case = next((c for c in cases if c.id == run["caseId"]), None)
        failure = run.get("failure") or {}
        issue = self.issues.create(
            title=case.name if case else run["caseId"],
            apis=[a for a in (case.api_ids() if case else []) if a != "token"],
            team=self.settings.team,
            first_seen=run["startedAt"][:10],
            report_status="발견",
            symptom=f"{failure.get('actual', '')}. {failure.get('reason', '')}".strip(". "),
            cases=[run["caseId"]],
        )
        self.store.set_match(run_id, {"kind": "known", "issueId": issue.id})
        updated = self.store.get(run_id)
        self.events.publish("run", updated)
        self.events.publish("issue", issue.to_api())
        return issue.to_api()

    def status(self) -> dict[str, Any]:
        s = self.settings
        _, problems = self.load()

        def has(*keys: Any) -> bool:
            return all(k is not None and k.get_secret_value() for k in keys)

        return {
            "env": s.nh_env,
            "baseUrl": s.base_url,
            "domesticKey": has(s.nh_app_key, s.nh_app_secret),
            "overseasKey": has(s.nh_overseas_app_key, s.nh_overseas_app_secret),
            "apiCount": len(self.apis),
            "caseProblems": problems,
            "queued": self._queue.qsize(),
        }
