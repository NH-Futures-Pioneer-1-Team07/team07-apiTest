"""실행 기록 저장 (SQLite). 실행 하나를 JSON 한 줄로 둔다. 요청·응답 원문도 그대로 들어간다."""

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any


class RunStore:
    def __init__(self, path: Path):
        if str(path) != ":memory:":
            path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, case_id TEXT NOT NULL, status TEXT NOT NULL, started_at TEXT NOT NULL, data TEXT NOT NULL)"
            )
            self._db.execute("CREATE INDEX IF NOT EXISTS runs_case ON runs(case_id, started_at)")
            # 서버가 실행 중에 꺼졌다면 진행중으로 남은 기록을 오류로 바꾼다
            for (rid, data) in self._db.execute("SELECT id, data FROM runs WHERE status = 'running'").fetchall():
                run = json.loads(data)
                run.update(status="error", errorKind="연결 실패", errorReason="실행 중에 서버가 종료되었습니다")
                self._db.execute("UPDATE runs SET status = ?, data = ? WHERE id = ?", ("error", json.dumps(run, ensure_ascii=False), rid))
            self._db.commit()

    def save(self, run: dict[str, Any]) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO runs (id, case_id, status, started_at, data) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET status = excluded.status, data = excluded.data",
                (run["id"], run["caseId"], run["status"], run["startedAt"], json.dumps(run, ensure_ascii=False)),
            )
            self._db.commit()

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute("SELECT data FROM runs WHERE id = ?", (run_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, limit: int = 3000, with_steps: bool = True) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute("SELECT data FROM runs ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()
        runs = [json.loads(r[0]) for r in rows]
        if not with_steps:
            for r in runs:
                r["steps"] = []
        return runs

    def latest_ids(self) -> set[str]:
        """케이스마다 가장 최근 실행의 id."""
        with self._lock:
            rows = self._db.execute(
                "SELECT id FROM runs r WHERE started_at = (SELECT MAX(started_at) FROM runs WHERE case_id = r.case_id)"
            ).fetchall()
        return {r[0] for r in rows}

    def set_match(self, run_id: str, match: dict[str, Any]) -> None:
        run = self.get(run_id)
        if run:
            run["match"] = match
            self.save(run)
