import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { apiById, cases, useStore } from "../store";
import { CaseReportBadge, fmtDuration, fmtTime, PageHeader, RecheckTag, STATUS_LABEL, StatusBadge } from "../components/ui";
import type { RunStatus } from "../data/types";

const STATUSES: (RunStatus | "all")[] = ["all", "success", "fail", "running", "error", "skipped"];
const allTags = [...new Set(cases.flatMap((c) => c.tags))];

export function TestList() {
  const { latestByCase, runCase, runCases, caseIssue } = useStore();
  const [recheckOnly, setRecheckOnly] = useState(false);
  const [params, setParams] = useSearchParams();
  const [status, setStatus] = useState<RunStatus | "all">((params.get("status") as RunStatus) ?? "all");
  const [kind, setKind] = useState<"전체" | "단일" | "시나리오">("전체");
  const [tag, setTag] = useState("");
  const [q, setQ] = useState("");
  const matchFilter = params.get("match"); // new | changed

  const rows = cases
    .map((c) => ({ c, r: latestByCase.get(c.id) }))
    .filter(
      ({ c, r }) =>
        (status === "all" || r?.status === status) &&
        (kind === "전체" || c.kind === kind) &&
        (tag === "" || c.tags.includes(tag)) &&
        (!recheckOnly || caseIssue.has(c.id)) &&
        (!matchFilter || r?.match?.kind === matchFilter) &&
        (q === "" || `${c.name} ${c.id} ${c.apiIds.join(" ")}`.toLowerCase().includes(q.toLowerCase())),
    );

  return (
    <>
      <PageHeader
        title="테스트 목록"
        sub="케이스별 최근 실행 결과. 케이스 파일은 testcases/nh-futures/ 에 있습니다"
        actions={
          <button className="btn primary" onClick={() => runCases(rows.map(({ c }) => c.id))}>
            보이는 케이스 실행 ({rows.length})
          </button>
        }
      />

      <div className="filters">
        <div className="seg">
          {STATUSES.map((s) => (
            <button key={s} className={status === s ? "on" : ""} onClick={() => setStatus(s)}>
              {s === "all" ? "전체" : STATUS_LABEL[s]}
            </button>
          ))}
        </div>
        <div className="seg">
          {(["전체", "단일", "시나리오"] as const).map((k) => (
            <button key={k} className={kind === k ? "on" : ""} onClick={() => setKind(k)}>{k}</button>
          ))}
        </div>
        <select value={tag} onChange={(e) => setTag(e.target.value)}>
          <option value="">모든 태그</option>
          {allTags.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <label className="check">
          <input type="checkbox" checked={recheckOnly} onChange={(e) => setRecheckOnly(e.target.checked)} />
          제보 재확인 케이스만
        </label>
        {matchFilter && (
          <button className="chip" onClick={() => setParams({})}>
            {matchFilter === "new" ? "기존 제보 없는 실패만" : "NH 설명과 달라진 것만"} ✕
          </button>
        )}
        <input className="search" placeholder="케이스, API 검색" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>

      <section className="card flush">
        <table className="table">
          <thead>
            <tr>
              <th>상태</th>
              <th>케이스</th>
              <th>유형</th>
              <th>대상 API</th>
              <th>태그</th>
              <th>제보</th>
              <th>실행 시각</th>
              <th className="r">소요</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ c, r }) => (
              <tr key={c.id}>
                <td>{r && <StatusBadge status={r.status} />}</td>
                <td>
                  <Link to={`/tests/${c.id}`} className="strong">{c.name}</Link>
                  <div className="row wrap small case-meta"><span className="muted mono">{c.id}</span><RecheckTag caseId={c.id} /></div>
                </td>
                <td className="small">{c.kind}</td>
                <td className="small">
                  {c.apiIds.filter((a) => a !== "token" || c.apiIds.length === 1).map((a) => (
                    <div key={a}><Link to={`/apis/${a}`}>{apiById.get(a)?.name ?? a}</Link></div>
                  ))}
                </td>
                <td>{c.tags.map((t) => <span key={t} className="tag">{t}</span>)}</td>
                <td>
                  <CaseReportBadge caseId={c.id} run={r} />
                </td>
                <td className="muted small nowrap">{r && fmtTime(r.startedAt)}</td>
                <td className="r small">{r && fmtDuration(r.durationMs)}</td>
                <td>
                  <button className="btn sm" disabled={r?.status === "running"} onClick={() => runCase(c.id)}>실행</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </>
  );
}
