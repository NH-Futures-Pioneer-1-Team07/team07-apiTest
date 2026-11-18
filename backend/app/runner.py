"""테스트 케이스 실행.

실행 결과(Run)는 화면이 그대로 쓰는 형식의 사전이다. 키 이름은 화면과 맞추려고 camelCase 를 쓴다.

상태
- success: 모든 판정 규칙 통과
- fail: 판정 규칙이 하나 이상 맞지 않음. 제한 시간 초과도 여기에 넣는다 (서버가 제때 응답하지 못함)
- error: 테스트 자체를 실행하지 못함 (연결 실패, 키 없음, 케이스 파일 오류)
- skipped: 실행 조건 밖 (시간대, 실전 차단)
"""

import time
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

from app.cases import Case, Check, Step, validate_case
from app.catalog import Api
from app.checks import MISSING, Context, Result, evaluate_check, field_results, resolve
from app.config import Settings
from app.expr import ExprError, as_number, evaluate, get_path, render
from app.market import condition_met, domestic_state, now_kst
from app.nh import AuthFailed, ConfigMissing, Exchange, NHClient

MAX_BODY_CHARS = 30_000
Progress = Callable[[dict[str, Any]], None]


class CaseError(Exception):
    def __init__(self, kind: str, reason: str):
        super().__init__(reason)
        self.kind = kind
        self.reason = reason


def _all_nines(key: Any) -> bool:
    s = str(key or "").strip()
    return len(s) > 8 and set(s) == {"9"}


def _clip(text: str) -> str:
    if len(text) <= MAX_BODY_CHARS:
        return text
    return text[:MAX_BODY_CHARS] + f"\n… (원문 {len(text):,}자 중 {MAX_BODY_CHARS:,}자만 저장)"


def _match_row(rows: Any, where: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(rows, list):
        return None
    for row in rows:
        if isinstance(row, dict) and all(
            (as_number(row.get(k)) == as_number(v)) if isinstance(as_number(v), (int, float)) else str(row.get(k)) == str(v)
            for k, v in where.items()
        ):
            return row
    return None


class Runner:
    def __init__(
        self,
        settings: Settings,
        apis: dict[str, Api],
        client: NHClient,
        clock: Callable[[], datetime] = now_kst,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.settings = settings
        self.apis = apis
        self.client = client
        self.clock = clock
        self.sleep = sleep

    # ---------- 케이스 ----------

    def new_run(self, case: Case) -> dict[str, Any]:
        now = self.clock()
        return {
            "id": f"R-{now.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}",
            "caseId": case.id,
            "status": "running",
            "startedAt": now.isoformat(),
            "durationMs": 0,
            "env": "모의" if self.settings.nh_env == "mock" else "실전",
            "market": domestic_state(now),
            "steps": [],
        }

    def run(self, case: Case, issue_id: str | None = None, run: dict[str, Any] | None = None, progress: Progress | None = None) -> dict[str, Any]:
        run = run or self.new_run(case)
        started = time.monotonic()
        notify = progress or (lambda r: None)
        now = self.clock()

        unmet = [c for c in case.when if not condition_met(c, now)]
        if unmet:
            return self._finish(run, started, "skipped", skipKind="시간대 조건 밖", skipReason=f"실행 조건 밖: {', '.join(unmet)} 아님")
        if self.settings.nh_env == "real" and not self.settings.allow_real_orders and any(
            self.apis[a].is_order for a in case.api_ids() if a in self.apis
        ):
            return self._finish(run, started, "skipped", skipKind="실전 차단", skipReason="실전 환경에서는 주문·정정·취소 케이스를 실행하지 않습니다")
        problems = validate_case(case, self.apis)
        if problems:
            return self._finish(run, started, "error", errorKind="케이스 파일 오류", errorReason="; ".join(problems))

        variables: dict[str, Any] = {}
        failed = False
        error: CaseError | None = None
        for step in case.steps:
            if failed or error:
                run["steps"].append({"name": step.name, "apiId": step.api, "status": "skipped", "durationMs": 0, "assertions": [], "note": "앞 단계가 실패해서 실행하지 않음"})
                continue
            try:
                ok = self._step(step, variables, run, notify)
                failed = failed or not ok
            except CaseError as e:
                error = e
        for step in case.cleanup:
            if step.if_failed and not (failed or error):
                run["steps"].append({"name": step.name, "apiId": step.api, "status": "skipped", "durationMs": 0, "assertions": [], "note": "앞 단계가 모두 성공해서 정리할 것이 없음"})
                continue
            try:
                self._step(step, variables, run, notify, cleanup=True)
            except CaseError as e:
                run["steps"].append({"name": step.name, "apiId": step.api, "status": "error", "durationMs": 0, "assertions": [], "note": f"정리 단계 실행 실패: {e.reason}"})

        if error:
            return self._finish(run, started, "error", errorKind=error.kind, errorReason=error.reason)
        status = "fail" if failed else "success"
        extra: dict[str, Any] = {}
        if failed:
            extra["failure"] = self._failure(run)
        match = self._match(case, issue_id, status)
        if match:
            extra["match"] = match
        return self._finish(run, started, status, **extra)

    def _finish(self, run: dict[str, Any], started: float, status: str, **extra: Any) -> dict[str, Any]:
        run.update(status=status, durationMs=int((time.monotonic() - started) * 1000), **extra)
        return run

    @staticmethod
    def _failure(run: dict[str, Any]) -> dict[str, str]:
        for s in run["steps"]:
            if s["status"] != "fail" or s.get("superseded"):
                continue
            for a in s["assertions"]:
                if not a["passed"]:
                    return {
                        "expected": f"{a['rule']}: {a['expected']}",
                        "actual": a["actual"],
                        "reason": f"[{s['name']}] {a['rule']} 규칙 실패. 기대 {a['expected']}, 실제 {a['actual']}",
                    }
        return {"expected": "-", "actual": "-", "reason": "실패한 단계가 있습니다"}

    @staticmethod
    def _match(case: Case, issue_id: str | None, status: str) -> dict[str, str] | None:
        issue = issue_id or case.issue
        if issue:
            if status == case.issue_result:
                return {"kind": "known", "issueId": issue} if status == "fail" else None
            return {"kind": "changed", "issueId": issue}
        return {"kind": "new"} if status == "fail" else None

    # ---------- 단계 ----------

    def _step(self, step: Step, variables: dict[str, Any], run: dict[str, Any], notify: Progress, cleanup: bool = False) -> bool:
        api = self.apis[step.api]
        each_list = [render(e, variables) for e in step.each] if step.each else []
        variants = [(f"{step.name} ({', '.join(f'{k}={v}' for k, v in e.items())})", e) for e in each_list] if step.each else [(step.name, {})]
        all_ok = True
        for name, each in variants:
            scope = {**variables, **each}
            try:
                body = render({**(step.body or {}), **each}, scope)
            except ExprError as e:
                if cleanup:
                    run["steps"].append({"name": name, "apiId": step.api, "status": "skipped", "durationMs": 0, "assertions": [], "note": f"건너뜀: {e}"})
                    notify(run)
                    continue
                raise CaseError("케이스 파일 오류", str(e)) from None
            checks = [Check.model_validate(render(c.model_dump(by_alias=True, exclude_none=True), scope)) for c in step.expect]
            if step.api == "token":
                ok = self._token_step(step, name, checks, scope, run)
            elif step.paginate:
                ok = self._paginated(step, api, name, body, checks, scope, run, notify)
            else:
                ok = self._single(step, api, name, body, checks, scope, run)
            variables.update({k: v for k, v in scope.items() if k in step.extract})
            all_ok = all_ok and ok
            notify(run)
        return all_ok

    def _call(self, api: Api, body: dict[str, Any], step: Step) -> list[Exchange]:
        try:
            attempts = self.client.send(api, body, timeout_s=step.timeout_s, auth=step.auth)
        except ConfigMissing as e:
            raise CaseError("인증 설정 누락", str(e)) from None
        except AuthFailed as e:
            raise CaseError("인증 실패", str(e)) from None
        except ConnectionError as e:
            raise CaseError("연결 실패", str(e)) from None
        last = attempts[-1]
        if last.error and not last.timed_out:
            raise CaseError("연결 실패", f"{api.url}: {last.error}")
        return attempts

    def _record(self, name: str, api_id: str, ex: Exchange, results: list[Result], **extra: Any) -> dict[str, Any]:
        ok = all(r.passed for r in results)
        rec: dict[str, Any] = {
            "name": name,
            "apiId": api_id,
            "status": "success" if ok else "fail",
            "durationMs": ex.duration_ms,
            "request": {"method": ex.method, "url": ex.url, "headers": ex.request_headers, "body": ex.request_body},
            "response": None
            if ex.status is None
            else {"status": ex.status, "headers": ex.response_headers, "body": _clip(ex.response_text)},
            "assertions": [r.to_dict() for r in results],
        }
        notes = [n for n in (ex.note, extra.pop("note", None)) if n]
        if notes:
            rec["note"] = " / ".join(notes)
        rec.update({k: v for k, v in extra.items() if v})
        return rec

    def _judge(self, ex: Exchange, checks: list[Check], step: Step, row: dict[str, Any] | None = None, rows: list[Any] | None = None) -> list[Result]:
        if ex.timed_out:
            return [Result("응답 시간", False, f"≤ {step.timeout_s:.0f}초", f"{step.timeout_s:.0f}초 안에 응답 없음")]
        ctx = Context(status=ex.status, body=ex.body, text=ex.response_text, duration_ms=ex.duration_ms, row=row, rows=rows)
        results: list[Result] = []
        for c in checks:
            results.extend(evaluate_check(c, ctx))
        return results

    def _extract(self, step: Step, ex: Exchange, row: dict[str, Any] | None, scope: dict[str, Any]) -> dict[str, str]:
        got: dict[str, str] = {}
        ctx = Context(status=ex.status, body=ex.body, text=ex.response_text, duration_ms=ex.duration_ms, row=row)
        for var, spec in step.extract.items():
            path = spec if isinstance(spec, str) else spec.path
            value = resolve(ctx, path)
            if value is MISSING:
                continue
            if not isinstance(spec, str) and spec.expr:
                value = evaluate(spec.expr, {"value": value})
            if not isinstance(spec, str) and spec.format:
                value = spec.format.format(value)
            scope[var] = value
            got[var] = str(value)
        return got

    def _token_step(self, step: Step, name: str, checks: list[Check], scope: dict[str, Any], run: dict[str, Any]) -> bool:
        market = step.market or "domestic"
        try:
            ex = self.client.request_token(market, timeout_s=step.timeout_s)
        except ConfigMissing as e:
            raise CaseError("인증 설정 누락", str(e)) from None
        if ex.error and not ex.timed_out:
            raise CaseError("연결 실패", ex.error)
        results = self._judge(ex, checks, step)
        rec = self._record(name, "token", ex, results, extracted=self._extract(step, ex, None, scope))
        run["steps"].append(rec)
        return rec["status"] == "success"

    def _single(self, step: Step, api: Api, name: str, body: dict[str, Any], checks: list[Check], scope: dict[str, Any], run: dict[str, Any]) -> bool:
        waited = 0
        polls = 0
        deadline = time.monotonic() + (step.wait_until.timeout_s if step.wait_until else 0)
        while True:
            attempts = self._call(api, body, step)
            polls += 1
            ex = attempts[-1]
            for prev in attempts[:-1]:
                rec = self._record(f"{name} (다시 보내기 전)", api.id, prev, self._judge(prev, checks, step))
                rec["superseded"] = True
                run["steps"].append(rec)
            row = None
            if step.select and isinstance(ex.body, (dict, list)):
                where = render(step.select.where, scope)
                try:
                    row = _match_row(get_path(ex.body, step.select.path), where)
                except (KeyError, IndexError, ValueError):
                    row = None
            if step.wait_until and not ex.timed_out:
                ctx_val = resolve(Context(ex.status, ex.body, ex.response_text, ex.duration_ms, row=row), step.wait_until.path)
                met = all(r.passed for r in field_results(step.wait_until, ctx_val))
                if not met and time.monotonic() < deadline:
                    self.sleep(step.wait_until.interval_s)
                    waited += 1
                    continue
            break
        results = self._judge(ex, checks, step, row=row)
        note = None
        if step.wait_until:
            note = f"조건이 맞을 때까지 {polls}번 조회" + ("" if polls == 1 else f" (약 {waited * step.wait_until.interval_s:.0f}초 대기)")
        extracted = self._extract(step, ex, row, scope)
        rec = self._record(name, api.id, ex, results, extracted=extracted, note=note)
        run["steps"].append(rec)
        return rec["status"] == "success"

    def _paginated(self, step: Step, api: Api, name: str, body: dict[str, Any], checks: list[Check], scope: dict[str, Any], run: dict[str, Any], notify: Progress) -> bool:
        pg = step.paginate
        assert pg is not None
        all_rows: list[Any] = []
        seen_first: dict[str, int] = {}
        ok = True
        repeated: str | None = None
        last_key: Any = None
        stop_reason = f"최대 {pg.max_pages}페이지까지 받음"
        for page in range(1, pg.max_pages + 1):
            attempts = self._call(api, body, step)
            ex = attempts[-1]
            results = self._judge(ex, checks, step)
            rows = []
            if isinstance(ex.body, dict):
                try:
                    rows = get_path(ex.body, pg.rows)
                except (KeyError, IndexError, ValueError):
                    rows = []
            rows = rows if isinstance(rows, list) else []
            if rows:
                sig = str(rows[0])
                if sig in seen_first:
                    repeated = f"{page}페이지 첫 행이 {seen_first[sig]}페이지 첫 행과 같음"
                seen_first.setdefault(sig, page)
            all_rows.extend(rows)
            last_key = ex.body.get(pg.next_key) if isinstance(ex.body, dict) else None
            rec = self._record(f"{name} {page}페이지", api.id, ex, results, extracted={pg.next_key: str(last_key)} if last_key else None)
            run["steps"].append(rec)
            notify(run)
            ok = ok and rec["status"] == "success"
            if ex.timed_out or not rec["status"] == "success" or repeated:
                stop_reason = repeated or "실패해서 멈춤"
                break
            if not last_key or not rows:
                stop_reason = "다음 키가 없거나 빈 페이지라서 멈춤"
                break
            if _all_nines(last_key):
                stop_reason = "다음 키가 9로만 되어 있어 마지막 페이지로 보고 멈춤 (NH-005)"
                break
            body = {**body, pg.next_key: str(last_key)}
        summary = [Result("페이지 반복 없음", repeated is None, "같은 페이지가 다시 오지 않음", repeated or "반복 없음")]
        ctx = Context(status=200, body=None, text="", duration_ms=0, rows=all_rows)
        for c in pg.expect_all:
            summary.extend(evaluate_check(Check.model_validate(render(c.model_dump(by_alias=True, exclude_none=True), scope)), ctx))
        passed = all(r.passed for r in summary)
        run["steps"].append({
            "name": f"{name} 전체 {len(all_rows):,}행 합계",
            "apiId": api.id,
            "status": "success" if passed else "fail",
            "durationMs": 0,
            "assertions": [r.to_dict() for r in summary],
            "note": stop_reason,
        })
        return ok and passed
