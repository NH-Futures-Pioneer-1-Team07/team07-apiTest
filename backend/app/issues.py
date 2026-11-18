"""제보 내역. 제보 하나를 YAML 파일 하나로 레포에 둔다 (issues/nh-futures/NH-001.yaml).

Claude가 새 제보와 NH 답변을 파일로 기록할 수 있고, 화면에서 상태를 바꾸면 파일에 다시 쓴다.
"""

import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict

from app.market import KST

ReportStatus = Literal["발견", "제보 완료", "답변 받음"]
Conclusion = Literal["명세 수정 예정", "명세 수정 완료", "의도된 동작", "모의 환경 한정", "NH 확인 중"]


class Issue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    apis: list[str] = []
    team: str = ""
    first_seen: str = "-"
    reported_at: str | None = None
    answered_at: str | None = None
    report_status: ReportStatus = "발견"
    conclusion: Conclusion | None = None
    symptom: str = ""
    nh_answer: str | None = None
    rules: list[str] = []
    pending: list[str] = []
    cases: list[str] = []  # 이 제보를 재확인하는 테스트 케이스
    evidence: str | None = None  # 재현 기록 폴더 (레포 기준 경로)

    def to_api(self) -> dict[str, Any]:
        """화면 형식 (camelCase)."""
        return {
            "id": self.id,
            "title": self.title,
            "apiIds": self.apis,
            "team": self.team,
            "firstSeen": self.first_seen,
            "reportedAt": self.reported_at,
            "answeredAt": self.answered_at,
            "reportStatus": self.report_status,
            "conclusion": self.conclusion,
            "symptom": self.symptom,
            "nhAnswer": self.nh_answer,
            "rules": self.rules,
            "pending": self.pending,
            "cases": self.cases,
            "evidence": self.evidence,
        }


class _Dumper(yaml.SafeDumper):
    pass


def _str_presenter(dumper: yaml.SafeDumper, data: str) -> yaml.Node:
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_Dumper.add_representer(str, _str_presenter)


class IssueStore:
    def __init__(self, directory: Path):
        self.dir = directory
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, issue_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", issue_id):
            raise ValueError(f"잘못된 제보 ID: {issue_id}")
        return self.dir / f"{issue_id}.yaml"

    def list(self) -> list[Issue]:
        out = []
        for p in sorted(self.dir.glob("*.yaml")):
            out.append(Issue.model_validate(yaml.safe_load(p.read_text("utf-8"))))
        return out

    def get(self, issue_id: str) -> Issue | None:
        p = self._path(issue_id)
        return Issue.model_validate(yaml.safe_load(p.read_text("utf-8"))) if p.exists() else None

    def save(self, issue: Issue) -> None:
        data = issue.model_dump(exclude_defaults=False)
        text = yaml.dump(data, Dumper=_Dumper, allow_unicode=True, sort_keys=False, width=1000)
        self._path(issue.id).write_text(text, "utf-8")

    def set_status(self, issue_id: str, status: ReportStatus) -> Issue:
        with self._lock:
            issue = self.get(issue_id)
            if issue is None:
                raise KeyError(issue_id)
            today = datetime.now(KST).strftime("%Y-%m-%d")
            issue.report_status = status
            if status == "제보 완료" and not issue.reported_at:
                issue.reported_at = today
            if status == "답변 받음" and not issue.answered_at:
                issue.answered_at = today
            self.save(issue)
            return issue

    def create(self, **fields: Any) -> Issue:
        with self._lock:
            nums = [int(m.group(1)) for p in self.dir.glob("*.yaml") if (m := re.search(r"(\d+)$", p.stem))]
            prefix = next((re.sub(r"\d+$", "", p.stem) for p in self.dir.glob("*.yaml")), "NH-")
            issue = Issue(id=f"{prefix}{(max(nums) if nums else 0) + 1:03d}", **fields)
            self.save(issue)
            return issue
