import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { apis, cases, useStore } from "../store";
import { FailReportTag, PageHeader, StatusBadge } from "../components/ui";
import type { RunStatus } from "../data/types";

const REGIONS = ["전체", "국내", "해외", "공통"] as const;
const CATEGORIES = ["전체", "시세", "계좌", "주문", "인증", "실시간"] as const;

export function ApiList() {
  const { latestByCase } = useStore();
  const [region, setRegion] = useState<(typeof REGIONS)[number]>("전체");
  const [category, setCategory] = useState<(typeof CATEGORIES)[number]>("전체");
  const [q, setQ] = useState("");
  const [onlyTested, setOnlyTested] = useState(false);

  const rows = useMemo(() => {
    return apis.map((api) => {
      const related = cases.filter((c) => c.apiIds.includes(api.id));
      const statuses = related.map((c) => latestByCase.get(c.id)?.status).filter(Boolean) as RunStatus[];
      const worst: RunStatus | undefined = (["running", "fail", "error", "success", "skipped"] as RunStatus[]).find((s) =>
        statuses.includes(s),
      );
      return { api, caseCount: related.length, worst };
    });
  }, [latestByCase]);

  const filtered = rows.filter(
    ({ api, caseCount }) =>
      (region === "전체" || api.region === region) &&
      (category === "전체" || api.category === category) &&
      (!onlyTested || caseCount > 0) &&
      (q === "" || `${api.name} ${api.url} ${api.id}`.toLowerCase().includes(q.toLowerCase())),
  );

  const untested = rows.filter((r) => r.caseCount === 0).length;

  return (
    <>
      <PageHeader
        title="API 목록"
        sub={`NH선물 API 문서 ${apis.length}개 · 테스트 없는 API ${untested}개`}
        actions={
          <>
            <button className="btn" title="MD 문서 폴더를 다시 읽는다 (샘플에서는 동작하지 않음)">문서 다시 읽기</button>
            <button className="btn" disabled title="확장 단계">Swagger URL</button>
            <button className="btn" disabled title="확장 단계">엑셀 업로드</button>
          </>
        }
      />

      <div className="filters">
        <div className="seg">
          {REGIONS.map((r) => (
            <button key={r} className={region === r ? "on" : ""} onClick={() => setRegion(r)}>{r}</button>
          ))}
        </div>
        <div className="seg">
          {CATEGORIES.map((c) => (
            <button key={c} className={category === c ? "on" : ""} onClick={() => setCategory(c)}>{c}</button>
          ))}
        </div>
        <label className="check">
          <input type="checkbox" checked={onlyTested} onChange={(e) => setOnlyTested(e.target.checked)} />
          테스트 있는 API만
        </label>
        <input className="search" placeholder="API 명, URL 검색" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>

      <section className="card flush">
        <table className="table">
          <thead>
            <tr>
              <th>API 명</th>
              <th>URL</th>
              <th>방식</th>
              <th>제한 유형</th>
              <th className="r">케이스</th>
              <th>실패 제보</th>
              <th>최근 결과</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(({ api, caseCount, worst }) => (
              <tr key={api.id}>
                <td>
                  <Link to={`/apis/${api.id}`} className="strong">{api.name}</Link>
                  <div className="muted small mono">{api.id}</div>
                </td>
                <td className="mono small">{api.url}</td>
                <td><span className={`method m-${api.protocol === "WS" ? "ws" : api.method.toLowerCase()}`}>{api.protocol === "WS" ? "WS" : api.method}</span></td>
                <td className="small">{api.category}</td>
                <td className="r">{caseCount || <span className="muted">0</span>}</td>
                <td><FailReportTag apiId={api.id} /></td>
                <td>{worst ? <StatusBadge status={worst} /> : <span className="muted small">테스트 없음</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </>
  );
}
