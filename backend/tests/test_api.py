import time

import httpx
import yaml
from fastapi.testclient import TestClient

from app.issues import Issue, IssueStore
from app.main import create_app
from app.nh import NHClient
from app.service import Service
from tests.conftest import ok


def test_run_case_through_http_api(settings, fake):
    settings.cases_dir.mkdir(parents=True)
    (settings.cases_dir / "TC-1.yaml").write_text(yaml.safe_dump({
        "id": "TC-1", "name": "국내 일봉", "tags": ["시세"],
        "steps": [{"name": "조회", "api": "domestic_chart-daily", "body": {"nght_tp": "1", "sym": "X", "req_qty": "3000"}, "expect": [{"count": {"path": "Occurs1", "eq": 3000}}]}],
    }, allow_unicode=True), "utf-8")
    IssueStore(settings.issues_dir).save(Issue(id="NH-001", title="기존 제보", report_status="답변 받음"))
    fake.on("/trade/v1/domestic/chart-daily", ok({"Occurs1": [{}] * 1000}))

    client = NHClient(settings, http=httpx.Client(transport=httpx.MockTransport(fake)), sleep=lambda _: None)
    app = create_app(Service(settings, client=client))
    with TestClient(app) as http:
        assert http.get("/api/status").json()["domesticKey"] is True
        assert len(http.get("/api/apis").json()) == 50
        cases = http.get("/api/cases").json()
        assert cases[0]["kind"] == "단일" and cases[0]["issueId"] is None

        run_id = http.post("/api/runs", json={"caseIds": ["TC-1"]}).json()["runIds"][0]
        for _ in range(100):
            run = http.get(f"/api/runs/{run_id}").json()
            if run["status"] != "running":
                break
            time.sleep(0.05)
        assert run["status"] == "fail"
        assert run["match"] == {"kind": "new"}

        # 실패를 제보로 등록하면 새 제보가 생기고 케이스가 그 제보의 재확인 케이스가 된다
        issue = http.post("/api/issues", json={"runId": run_id}).json()
        assert issue["id"] == "NH-002" and issue["reportStatus"] == "발견" and issue["cases"] == ["TC-1"]
        assert http.get(f"/api/runs/{run_id}").json()["match"] == {"kind": "known", "issueId": "NH-002"}
        assert http.get("/api/cases").json()[0]["issueId"] == "NH-002"

        patched = http.patch("/api/issues/NH-002", json={"reportStatus": "제보 완료"}).json()
        assert patched["reportStatus"] == "제보 완료" and patched["reportedAt"]
        assert (settings.issues_dir / "NH-002.yaml").exists()

        assert http.post("/api/runs", json={"caseIds": ["없음"]}).status_code == 404
