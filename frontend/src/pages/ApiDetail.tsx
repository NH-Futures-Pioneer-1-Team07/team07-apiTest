import { Link, useParams } from "react-router-dom";
import { apiById, cases, useStore } from "../store";
import { Code, ConclusionTag, Empty, fmtTime, MatchBadge, PageHeader, ReportBadge, StatCard, StatusBadge } from "../components/ui";
import type { ApiField } from "../data/types";

function FieldTable({ fields, input }: { fields: ApiField[]; input?: boolean }) {
  if (fields.length === 0) return <Empty>필드 없음</Empty>;
  return (
    <table className="table compact">
      <thead>
        <tr>
          <th>Key</th>
          <th>한글명</th>
          <th>Type</th>
          <th>길이</th>
          {input && <th>필수</th>}
          <th>설명</th>
        </tr>
      </thead>
      <tbody>
        {fields.map((f, i) => (
          <tr key={`${f.parent}.${f.key}.${i}`}>
            <td className="mono">
              {f.parent && <span className="muted">{f.parent}.</span>}
              {f.key}
            </td>
            <td>{f.name}</td>
            <td className="mono small">{f.type}</td>
            <td className="small">{f.length}</td>
            {input && <td>{f.required ? <span className="req">Y</span> : <span className="muted">N</span>}</td>}
            <td className="small pre">{f.description}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function ApiDetail() {
  const { id = "" } = useParams();
  const { runs, issues, latestByCase, runCases } = useStore();
  const api = apiById.get(id);
  if (!api) return <Empty>API를 찾을 수 없습니다: {id}</Empty>;

  const related = cases.filter((c) => c.apiIds.includes(api.id));
  const relatedIds = new Set(related.map((c) => c.id));
  const apiRuns = runs.filter((r) => relatedIds.has(r.caseId));
  const n = (s: string) => apiRuns.filter((r) => r.status === s).length;
  const apiIssues = issues.filter((i) => i.apiIds.includes(api.id));

  return (
    <>
      <div className="crumbs"><Link to="/apis">API 목록</Link> / {api.name}</div>
      <PageHeader
        title={api.name}
        sub={`${api.protocol === "WS" ? "WEBSOCKET" : api.method} ${api.url}`}
        actions={
          <button className="btn primary" disabled={related.length === 0} onClick={() => runCases(related.map((c) => c.id))}>
            이 API 테스트 실행
          </button>
        }
      />

      <section className="stats">
        <StatCard label="전체 실행" value={apiRuns.length} />
        <StatCard label="성공" value={n("success")} tone="success" />
        <StatCard label="실패" value={n("fail")} tone="fail" />
        <StatCard label="진행중" value={n("running")} tone="running" />
        <StatCard label="오류" value={n("error")} tone="error" />
      </section>

      <div className="grid-2">
        <section className="card">
          <h2>테스트 케이스 <span className="muted">{related.length}</span></h2>
          {related.length === 0 ? (
            <Empty>아직 테스트 케이스가 없습니다. Claude 채팅에서 "{api.id} 테스트 케이스 만들어줘"로 요청하세요.</Empty>
          ) : (
            <ul className="list">
              {related.map((c) => {
                const r = latestByCase.get(c.id);
                return (
                  <li key={c.id}>
                    {r && <StatusBadge status={r.status} />}
                    <Link to={`/tests/${c.id}`}>{c.name}</Link>
                    {r?.status === "fail" && <MatchBadge match={r.match} />}
                    {r && <span className="muted small push nowrap">{fmtTime(r.startedAt)}</span>}
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        <section className="card">
          <h2>제보와 사용 규칙 <span className="muted">{apiIssues.length}</span></h2>
          {apiIssues.length === 0 ? (
            <Empty>이 API에 대한 제보가 없습니다.</Empty>
          ) : (
            <ul className="list">
              {apiIssues.map((i) => (
                <li key={i.id} className="col">
                  <div className="row">
                    <Link to={`/issues/${i.id}`} className="mono">{i.id}</Link>
                    <span>{i.title}</span>
                    <span className="push"><ReportBadge status={i.reportStatus} /> <ConclusionTag value={i.conclusion} /></span>
                  </div>
                  {i.rules.map((rule) => (
                    <div key={rule} className="rule">규칙 · {rule}</div>
                  ))}
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <section className="card">
        <h2>기본 정보</h2>
        <dl className="kv">
          <dt>문서명</dt><dd className="mono">{api.id}</dd>
          <dt>분류</dt><dd>{api.region} · {api.category}</dd>
          <dt>Content-Type</dt><dd className="mono">{api.contentType || "application/json"}</dd>
          <dt>모의 Domain</dt><dd className="mono">{api.demoDomain}</dd>
          <dt>요청 제한</dt><dd>{api.limit}</dd>
        </dl>
        {api.description && <Code text={api.description} />}
      </section>

      <section className="card">
        <h2>INPUT</h2>
        <FieldTable fields={api.input} input />
      </section>
      <section className="card">
        <h2>OUTPUT</h2>
        <FieldTable fields={api.output} />
      </section>
      <div className="grid-2">
        <section className="card">
          <h2>Request 예시</h2>
          <Code text={api.requestExample} />
        </section>
        <section className="card">
          <h2>Response 예시</h2>
          <Code text={api.responseExample} />
        </section>
      </div>
    </>
  );
}
