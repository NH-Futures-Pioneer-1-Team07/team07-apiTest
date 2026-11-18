import { Link } from "react-router-dom";
import { apiById, caseById, cases, useStore } from "../store";
import { Empty, failReportCounts, FailReportTag, fmtTime, PageHeader, ReasonBreakdown, StatCard } from "../components/ui";
import { RecentFailures } from "../components/RecentFailures";
import type { RunStatus } from "../data/types";

export function Dashboard() {
  const { runs, issues, latestByCase, runCases } = useStore();
  const latest = [...latestByCase.values()];
  const count = (s: RunStatus) => latest.filter((r) => r.status === s).length;

  // 최근 14일 성공률 (건너뜀 제외)
  const byDay = new Map<string, { ok: number; total: number }>();
  for (const r of runs) {
    if (r.status === "skipped" || r.status === "running") continue;
    const day = new Date(new Date(r.startedAt).getTime() + 9 * 3600_000).toISOString().slice(5, 10);
    const v = byDay.get(day) ?? { ok: 0, total: 0 };
    v.total++;
    if (r.status === "success") v.ok++;
    byDay.set(day, v);
  }
  const days = [...byDay.entries()].sort(([a], [b]) => a.localeCompare(b)).slice(-14);

  // 미제보가 많은 API: 미제보 실패가 있는 API만, 미제보 건수 순, 같으면 누적 실패 횟수 순
  const failByApi = new Map<string, number>();
  for (const r of runs) {
    if (r.status !== "fail") continue;
    for (const a of caseById.get(r.caseId)?.apiIds ?? []) {
      if (a === "token") continue;
      failByApi.set(a, (failByApi.get(a) ?? 0) + 1);
    }
  }
  const unreportedOf = (id: string) => failReportCounts(id, latestByCase, issues).unreported;
  const topFail = [...failByApi.entries()]
    .filter(([id]) => unreportedOf(id) > 0)
    .sort((a, b) => unreportedOf(b[0]) - unreportedOf(a[0]) || b[1] - a[1]);
  const maxFail = Math.max(1, ...topFail.map(([, n]) => n));

  const lastRunAt = latest.map((r) => r.startedAt).sort().at(-1);

  return (
    <>
      <PageHeader
        title="대시보드"
        sub={`테스트 케이스 ${cases.length}개의 최근 실행 기준 · 마지막 실행 ${lastRunAt ? fmtTime(lastRunAt) : "-"}`}
        actions={
          <button className="btn primary" onClick={() => runCases(cases.map((c) => c.id))}>
            전체 실행
          </button>
        }
      />

      <section className="stats">
        <StatCard label="전체" value={latest.length} />
        <StatCard label="성공" value={count("success")} tone="success" />
        <StatCard label="실패" value={count("fail")} tone="fail" />
        <StatCard label="진행중" value={count("running")} tone="running" />
        <StatCard
          label="오류"
          value={count("error")}
          tone="error"
          sub={<ReasonBreakdown reasons={latest.filter((r) => r.status === "error").map((r) => r.errorKind)} />}
        />
        <StatCard
          label="건너뜀"
          value={count("skipped")}
          tone="skipped"
          sub={<ReasonBreakdown reasons={latest.filter((r) => r.status === "skipped").map((r) => r.skipKind)} />}
        />
      </section>

      <div className="grid-2">
        <section className="card">
          <h2>일별 성공률</h2>
          <div className="bars">
            {days.map(([day, v]) => {
              const pct = Math.round((v.ok / v.total) * 100);
              return (
                <div className="bar-col" key={day} title={`${day} · ${v.ok}/${v.total}건 성공`}>
                  <div className="bar-pct">{pct}</div>
                  <div className="bar-track">
                    <div className="bar-fill" style={{ height: `${pct}%` }} />
                  </div>
                  <div className="bar-label">{day.slice(3)}</div>
                </div>
              );
            })}
          </div>
        </section>

        <section className="card">
          <h2>미제보가 많은 API <span className="muted">{topFail.length}</span></h2>
          {topFail.length === 0 && <Empty>지금 실패 중인 테스트는 모두 제보되었습니다.</Empty>}
          <ul className="rank rank-scroll">
            {topFail.map(([id, n]) => (
              <li key={id}>
                <Link to={`/apis/${id}`}>{apiById.get(id)?.name ?? id}</Link>
                <div className="rank-bar">
                  <div style={{ width: `${(n / maxFail) * 100}%` }} />
                </div>
                <span className="num">{n}</span>
                <FailReportTag apiId={id} full />
              </li>
            ))}
          </ul>
        </section>
      </div>

      <RecentFailures />
    </>
  );
}
