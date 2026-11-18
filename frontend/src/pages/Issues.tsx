import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { apiById, cases, useStore } from "../store";
import { Code, ConclusionTag, Empty, fmtTime, PageHeader, ReportBadge, StatusBadge } from "../components/ui";
import type { Conclusion, Issue, ReportStatus } from "../data/types";

const REPORTS: (ReportStatus | "")[] = ["", "발견", "제보 완료", "답변 받음"];
const CONCLUSIONS: Conclusion[] = ["명세 수정 예정", "명세 수정 완료", "의도된 동작", "모의 환경 한정", "NH 확인 중"];
const OUR_TEAM = "team-07";

export function IssueList() {
  const { issues, latestByCase, caseIssue } = useStore();
  const [params, setParams] = useSearchParams();
  const report = (params.get("report") ?? "") as ReportStatus | "";
  const conclusion = params.get("conclusion") ?? "";
  const [ours, setOurs] = useState(false);

  const set = (k: string, v: string) => {
    const p = new URLSearchParams(params);
    if (v) p.set(k, v);
    else p.delete(k);
    setParams(p);
  };

  const rows = issues
    .filter(
      (i) =>
        (report === "" || i.reportStatus === report) &&
        (conclusion === "" || i.conclusion === conclusion) &&
        (!ours || i.team === OUR_TEAM),
    )
    .sort((a, b) => b.id.localeCompare(a.id));

  return (
    <>
      <PageHeader
        title="제보 내역"
        sub={`전체 ${issues.length}건 · 우리 팀 ${issues.filter((i) => i.team === OUR_TEAM).length}건 · 다른 팀 제보도 함께 관리해서 중복 제보를 막습니다`}
      />

      <div className="filters">
        <div className="seg">
          {REPORTS.map((r) => (
            <button key={r} className={report === r ? "on" : ""} onClick={() => set("report", r)}>
              {r || "전체"} <span className="muted">{r ? issues.filter((i) => i.reportStatus === r).length : issues.length}</span>
            </button>
          ))}
        </div>
        <select value={conclusion} onChange={(e) => set("conclusion", e.target.value)}>
          <option value="">모든 결론</option>
          {CONCLUSIONS.map((c) => <option key={c}>{c}</option>)}
        </select>
        <label className="check">
          <input type="checkbox" checked={ours} onChange={(e) => setOurs(e.target.checked)} />
          우리 팀 제보만
        </label>
      </div>

      <section className="card flush">
        <table className="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>현상</th>
              <th>대상 API</th>
              <th>제보 팀</th>
              <th>제보일</th>
              <th>제보 상태</th>
              <th>결론</th>
              <th>재확인 케이스</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((i) => {
              const linked = cases.filter((c) => caseIssue.get(c.id) === i.id);
              return (
                <tr key={i.id}>
                  <td className="nowrap"><Link to={`/issues/${i.id}`} className="mono strong">{i.id}</Link></td>
                  <td><Link to={`/issues/${i.id}`}>{i.title}</Link></td>
                  <td className="small">{i.apiIds.map((a) => <div key={a}>{apiById.get(a)?.name ?? a}</div>)}</td>
                  <td className={i.team === OUR_TEAM ? "strong small" : "small"}>{i.team}</td>
                  <td className="small nowrap">{i.reportedAt ?? <span className="muted">미제보</span>}</td>
                  <td><ReportBadge status={i.reportStatus} /></td>
                  <td><ConclusionTag value={i.conclusion} /></td>
                  <td>
                    {linked.length === 0 ? (
                      <span className="muted small">없음</span>
                    ) : (
                      linked.map((c) => {
                        const r = latestByCase.get(c.id);
                        return (
                          <Link key={c.id} to={`/tests/${c.id}`} className="row small">
                            {r && <StatusBadge status={r.status} />} {c.id}
                          </Link>
                        );
                      })
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
    </>
  );
}

function draftText(issue: Issue, caseIssue: Map<string, string>) {
  const linked = cases.find((c) => caseIssue.get(c.id) === issue.id);
  const apiLines = issue.apiIds
    .map((a) => {
      const api = apiById.get(a);
      return api ? `${api.name} ${api.method} ${api.url}` : a;
    })
    .join(", ");
  return [
    `[제보] ${issue.title}`,
    "",
    `* 팀: ${issue.team}`,
    `* 환경: 모의 (apidemo.futures.co.kr), ${issue.firstSeen}`,
    `* 대상: ${apiLines}`,
    "* 재현 절차:",
    "   1. 접근토큰 발급",
    `   2. ${linked ? `테스트 케이스 ${linked.id} (${linked.name}) 의 요청으로 호출` : "(요청 본문)"}`,
    "* 기대 결과: ",
    `* 실제 결과: ${issue.symptom}`,
    "* 로그·캡처: 요청·응답 원문 첨부",
    "* 영향: ",
    "* 개선 제안: ",
  ].join("\n");
}

export function IssueDetail() {
  const { id = "" } = useParams();
  const { issues, runs, caseIssue, setReportStatus } = useStore();
  const [copied, setCopied] = useState(false);
  const issue = issues.find((i) => i.id === id);
  if (!issue) return <Empty>제보를 찾을 수 없습니다: {id}</Empty>;

  const linked = cases.filter((c) => caseIssue.get(c.id) === issue.id);
  const matchedRuns = runs
    .filter((r) => r.match && "issueId" in r.match && r.match.issueId === issue.id)
    .sort((a, b) => b.startedAt.localeCompare(a.startedAt))
    .slice(0, 8);
  const draft = draftText(issue, caseIssue);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(draft);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };

  return (
    <>
      <div className="crumbs"><Link to="/issues">제보 내역</Link> / {issue.id}</div>
      <PageHeader
        title={`${issue.id} ${issue.title}`}
        sub={`${issue.team} · 최초 관찰 ${issue.firstSeen}`}
        actions={
          <>
            {issue.reportStatus === "발견" && (
              <button className="btn primary" onClick={() => setReportStatus(issue.id, "제보 완료")}>제보 완료로 표시</button>
            )}
            {issue.reportStatus === "제보 완료" && (
              <button className="btn primary" onClick={() => setReportStatus(issue.id, "답변 받음")}>답변 받음으로 표시</button>
            )}
          </>
        }
      />

      <section className="card">
        <div className="progress">
          {(["발견", "제보 완료", "답변 받음"] as ReportStatus[]).map((s, i, arr) => {
            const cur = arr.indexOf(issue.reportStatus);
            const date = s === "발견" ? issue.firstSeen : s === "제보 완료" ? issue.reportedAt : issue.answeredAt;
            return (
              <div key={s} className={`progress-step${i <= cur ? " done" : ""}${i === cur ? " cur" : ""}`}>
                <div className="progress-dot" />
                <div>{s}</div>
                <div className="muted small">{i <= cur ? date ?? "-" : ""}</div>
              </div>
            );
          })}
          <div className="progress-step">
            <div className="muted small">결론</div>
            <ConclusionTag value={issue.conclusion} />
          </div>
        </div>
      </section>

      <div className="grid-2">
        <section className="card">
          <h2>현상</h2>
          <p>{issue.symptom}</p>
          <h3>대상 API</h3>
          <ul className="list">
            {issue.apiIds.map((a) => (
              <li key={a}><Link to={`/apis/${a}`}>{apiById.get(a)?.name ?? a}</Link><span className="mono muted small">{apiById.get(a)?.url}</span></li>
            ))}
          </ul>
        </section>
        <section className="card">
          <h2>NH 답변</h2>
          {issue.nhAnswer ? (
            <>
              <div className="muted small">{issue.answeredAt}</div>
              <p>{issue.nhAnswer}</p>
            </>
          ) : (
            <Empty>아직 답변이 없습니다.</Empty>
          )}
        </section>
      </div>

      <div className="grid-2">
        <section className="card">
          <h2>사용 규칙 · 명세 보정</h2>
          {issue.rules.length === 0 ? <Empty>없음</Empty> : issue.rules.map((r) => <div key={r} className="rule">{r}</div>)}
          <h3>남은 확인</h3>
          {issue.pending.length === 0 ? <Empty>없음</Empty> : (
            <ul className="bullets">{issue.pending.map((p) => <li key={p}>{p}</li>)}</ul>
          )}
        </section>
        <section className="card">
          <h2>연결된 테스트</h2>
          {linked.length === 0 && matchedRuns.length === 0 ? (
            <Empty>재확인 케이스가 없습니다. 제보마다 다시 확인할 테스트 1개를 두는 것이 원칙입니다.</Empty>
          ) : (
            <ul className="list">
              {linked.map((c) => (
                <li key={c.id}><span className="badge recheck">{issue.id} 재확인</span><Link to={`/tests/${c.id}`}>{c.name}</Link></li>
              ))}
              {matchedRuns.map((r) => (
                <li key={r.id}>
                  <StatusBadge status={r.status} />
                  <Link to={`/tests/${r.caseId}?run=${r.id}`}>{cases.find((c) => c.id === r.caseId)?.name}</Link>
                  <span className="muted small push">{fmtTime(r.startedAt)}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <section className="card">
        <div className="row">
          <h2>제보 초안</h2>
          <button className="btn sm push" onClick={copy}>{copied ? "복사됨" : "복사"}</button>
        </div>
        <Code text={draft} />
      </section>
    </>
  );
}
