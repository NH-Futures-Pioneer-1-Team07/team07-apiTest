import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { apiById, caseById, useStore } from "../store";
import { Empty, fmtTime, MatchBadge, reportStateOf } from "./ui";
import type { Run } from "../data/types";

const LIMIT = 10;

// 실패 내용 한 줄: 실패한 판정 규칙 이름. HTTP 상태보다 구체적인 규칙을 먼저 보여준다
function shortReason(run: Run) {
  if (run.status === "error") return run.errorKind ?? "원인 미분류";
  const failed = run.steps.flatMap((s) => s.assertions.filter((a) => !a.passed));
  const pick = failed.find((a) => a.rule !== "HTTP 상태") ?? failed[0];
  if (pick) return `${pick.rule} 실패`;
  return run.failure?.reason.split(/[:.]/)[0] ?? "-";
}

function fullReason(run: Run) {
  if (run.status === "error") return run.errorReason ?? "";
  if (!run.failure) return "";
  return `기대: ${run.failure.expected}\n실제: ${run.failure.actual}\n${run.failure.reason}`;
}

export function RecentFailures() {
  const { issues, latestByCase } = useStore();
  const [tab, setTab] = useState<"fail" | "error">("fail");

  const rows = useMemo(() => {
    const latest = [...latestByCase.values()].filter((r) => r.status === "fail" || r.status === "error");
    return latest.map((run) => {
      const state = reportStateOf(run.match, issues);
      return { run, unreported: run.status === "fail" && (!state || state.kind === "unreported") };
    });
  }, [issues, latestByCase]);

  const failCount = rows.filter((r) => r.run.status === "fail").length;
  const errorCount = rows.length - failCount;
  const shown = rows
    .filter((r) => r.run.status === tab)
    .sort((a, b) => Number(b.unreported) - Number(a.unreported) || b.run.startedAt.localeCompare(a.run.startedAt));

  return (
    <section className="card">
      <div className="row wrap card-head">
        <h2>최근 실패·오류</h2>
        <div className="seg">
          <button className={tab === "fail" ? "on" : ""} onClick={() => setTab("fail")}>
            실패 <span className="muted">{failCount}</span>
          </button>
          <button className={tab === "error" ? "on" : ""} onClick={() => setTab("error")}>
            오류 <span className="muted">{errorCount}</span>
          </button>
        </div>
        <Link to={`/tests?status=${tab}`} className="push small">테스트 목록에서 전체 보기 →</Link>
      </div>

      {shown.length === 0 ? (
        <Empty>{tab === "fail" ? "실패한 테스트가 없습니다." : "오류가 없습니다."}</Empty>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>케이스 / API</th>
              <th>{tab === "fail" ? "실패 내용" : "오류 원인"}</th>
              {tab === "fail" && <th>제보</th>}
              <th>최근 실행</th>
            </tr>
          </thead>
          <tbody>
            {shown.slice(0, LIMIT).map(({ run }) => {
              const c = caseById.get(run.caseId);
              const apiId = c?.apiIds.find((a) => a !== "token") ?? c?.apiIds[0];
              return (
                <tr key={run.id}>
                  <td>
                    <Link to={`/tests/${run.caseId}`}>{c?.name}</Link>
                    {apiId && <div className="muted small">{apiById.get(apiId)?.name ?? apiId}</div>}
                  </td>
                  <td title={fullReason(run)}>{shortReason(run)}</td>
                  {tab === "fail" && <td><MatchBadge match={run.match} /></td>}
                  <td className="nowrap small muted">{fmtTime(run.startedAt)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      {shown.length > LIMIT && <div className="muted small more">외 {shown.length - LIMIT}건</div>}
    </section>
  );
}
