import { Fragment, useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { apiById, caseById, useStore } from "../store";
import { Code, Empty, fmtDuration, fmtTime, MatchBadge, RecheckTag, PageHeader, STATUS_LABEL, StatusBadge } from "../components/ui";
import type { StepRun } from "../data/types";

function StepDetail({ step }: { step: StepRun }) {
  const api = apiById.get(step.apiId);
  return (
    <div className="step-detail">
      <div className="row">
        <StatusBadge status={step.status} />
        <strong>{step.name}</strong>
        <Link to={`/apis/${step.apiId}`} className="muted small">{api?.name ?? step.apiId}</Link>
        <span className="push muted small">{fmtDuration(step.durationMs)}</span>
      </div>
      {step.note && <div className="note">{step.note}</div>}

      {step.assertions.length > 0 && (
        <>
          <h3>판정 규칙</h3>
          <table className="table compact">
            <thead>
              <tr><th></th><th>규칙</th><th>기대</th><th>실제</th></tr>
            </thead>
            <tbody>
              {step.assertions.map((a, i) => (
                <tr key={i} className={a.passed ? "" : "row-fail"}>
                  <td>{a.passed ? <span className="ok">✓</span> : <span className="ng">✕</span>}</td>
                  <td>{a.rule}</td>
                  <td className="mono small">{a.expected}</td>
                  <td className="mono small">{a.actual}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {step.extracted && (
        <>
          <h3>꺼낸 변수</h3>
          <dl className="kv">
            {Object.entries(step.extracted).map(([k, v]) => (
              <Fragment key={k}><dt className="mono">{k}</dt><dd className="mono">{v}</dd></Fragment>
            ))}
          </dl>
        </>
      )}

      {step.request && (
        <>
          <h3>요청</h3>
          <div className="mono small req-line">
            <span className="method m-post">{step.request.method}</span> {step.request.url}
          </div>
          <Code text={Object.entries(step.request.headers).map(([k, v]) => `${k}: ${v}`).join("\n")} />
          <Code text={step.request.body} />
        </>
      )}
      {step.response ? (
        <>
          <h3>
            응답 <span className={`http http-${String(step.response.status)[0]}`}>{step.response.status}</span>
          </h3>
          <Code text={Object.entries(step.response.headers).map(([k, v]) => `${k}: ${v}`).join("\n")} />
          <Code text={step.response.body} />
        </>
      ) : (
        step.request && <Empty>응답 없음</Empty>
      )}
      {!step.request && <Empty>실행되지 않은 단계</Empty>}
    </div>
  );
}

export function TestDetail() {
  const { id = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const { runs, latestByCase, runCase, registerIssue, loadRun } = useStore();
  const testCase = caseById.get(id);
  const [stepIdx, setStepIdx] = useState(0);
  const [busy, setBusy] = useState(false);

  const history = runs.filter((r) => r.caseId === id).sort((a, b) => a.startedAt.localeCompare(b.startedAt));
  const run = history.find((r) => r.id === params.get("run")) ?? latestByCase.get(id);

  // 목록에는 최근 실행만 단계 원문이 있어서, 과거 실행을 고르면 따로 받는다
  useEffect(() => {
    if (run?.stepsOmitted) loadRun(run.id);
  }, [run?.id, run?.stepsOmitted, loadRun]);

  if (!testCase) return <Empty>테스트 케이스를 찾을 수 없습니다: {id}</Empty>;
  if (!run) {
    return (
      <>
        <div className="crumbs"><Link to="/tests">테스트 목록</Link> / {testCase.id}</div>
        <PageHeader
          title={testCase.name}
          sub={testCase.description}
          actions={<button className="btn primary" onClick={() => runCase(id)}>실행</button>}
        />
        <section className="card"><Empty>아직 실행 기록이 없습니다.</Empty></section>
      </>
    );
  }
  const step = run.steps[Math.min(stepIdx, run.steps.length - 1)];

  const register = async () => {
    setBusy(true);
    try {
      navigate(`/issues/${await registerIssue(run)}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="crumbs"><Link to="/tests">테스트 목록</Link> / {testCase.id}</div>
      <PageHeader
        title={testCase.name}
        sub={testCase.description}
        actions={
          <>
            {run.status === "fail" && run.match?.kind === "new" && (
              <button className="btn warn" disabled={busy} onClick={register}>
                제보 등록
              </button>
            )}
            <button className="btn primary" disabled={run.status === "running"} onClick={() => { setParams({}); runCase(id); }}>
              다시 실행
            </button>
          </>
        }
      />

      <section className={`card result result-${run.status}`}>
        <div className="row wrap">
          <StatusBadge status={run.status} large />
          <span className="muted">{fmtTime(run.startedAt)}</span>
          <span className="muted">· {fmtDuration(run.durationMs)}</span>
          <span className="muted">· {run.env} · {run.market}</span>
          <span className="muted mono small">· {run.id}</span>
          <span className="push row-inline"><RecheckTag caseId={id} /><MatchBadge match={run.match} /></span>
        </div>
        {run.failure && (
          <div className="failure">
            <div><div className="label">기대한 응답</div><div>{run.failure.expected}</div></div>
            <div><div className="label">실제 응답</div><div>{run.failure.actual}</div></div>
            <div className="span-2"><div className="label">잘못된 부분</div><div>{run.failure.reason}</div></div>
          </div>
        )}
        {run.errorReason && <div className="note">{run.errorReason}</div>}
        {run.skipReason && <div className="note">{run.skipReason}</div>}
        {run.status === "running" && <div className="note">실행 중입니다.</div>}
      </section>

      <section className="card">
        <h2>실행 이력 <span className="muted">{history.length}</span></h2>
        <div className="history">
          {history.map((h) => (
            <button
              key={h.id}
              className={`dot status-${h.status}${h.id === run.id ? " on" : ""}`}
              title={`${fmtTime(h.startedAt)} · ${STATUS_LABEL[h.status]}`}
              onClick={() => { setStepIdx(0); setParams({ run: h.id }); }}
            />
          ))}
        </div>
        <div className="muted small">왼쪽이 오래된 실행. 점을 누르면 그 실행을 봅니다.</div>
      </section>

      {run.steps.length === 0 ? (
        <section className="card"><Empty>{run.stepsOmitted ? "단계 기록을 불러오는 중…" : "이 실행에는 단계 기록이 없습니다."}</Empty></section>
      ) : (
        <div className="steps-layout">
          <section className="card steps">
            <h2>단계 <span className="muted">{run.steps.length}</span></h2>
            <ol>
              {run.steps.map((s, i) => (
                <li key={i} className={i === stepIdx ? "on" : ""} onClick={() => setStepIdx(i)}>
                  <span className={`dot sm status-${s.status}`} />
                  <span className="step-name">{s.name}{s.superseded && <span className="muted small"> · 다시 보내기 전</span>}</span>
                  <span className="muted small">{fmtDuration(s.durationMs)}</span>
                </li>
              ))}
            </ol>
          </section>
          <section className="card">{step && <StepDetail step={step} />}</section>
        </div>
      )}
    </>
  );
}
