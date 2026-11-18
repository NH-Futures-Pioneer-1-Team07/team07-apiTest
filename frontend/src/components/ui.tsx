import { Link } from "react-router-dom";
import type { Conclusion, Issue, IssueMatch, ReportStatus, Run, RunStatus } from "../data/types";
import { cases, useStore } from "../store";

export const STATUS_LABEL: Record<RunStatus, string> = {
  success: "성공",
  fail: "실패",
  running: "진행중",
  error: "오류",
  skipped: "건너뜀",
};

export function StatusBadge({ status, large }: { status: RunStatus; large?: boolean }) {
  return (
    <span className={`badge status-${status}${large ? " badge-lg" : ""}`}>
      {status === "running" && <span className="spinner" />}
      {STATUS_LABEL[status]}
    </span>
  );
}

export function ReportBadge({ status }: { status: ReportStatus }) {
  const cls = status === "발견" ? "report-found" : status === "제보 완료" ? "report-sent" : "report-answered";
  return <span className={`badge ${cls}`}>{status}</span>;
}

export function ConclusionTag({ value }: { value?: Conclusion }) {
  if (!value) return <span className="muted">-</span>;
  return <span className={`tag${value === "NH 확인 중" ? " tag-warn" : ""}`}>{value}</span>;
}

// 실패가 NH에 제보된 건인지. 제보 건에 연결만 되어 있고 아직 안 보냈으면 미제보로 본다
export type ReportState =
  | { kind: "unreported"; issue?: Issue } // issue 없음: 기존 제보 없음, issue 있음: 등록만 하고 안 보냄
  | { kind: "reported"; issue: Issue }
  | { kind: "changed"; issue: Issue };

export function reportStateOf(match: IssueMatch | undefined, issues: Issue[]): ReportState | undefined {
  if (!match) return undefined;
  if (match.kind === "new") return { kind: "unreported" };
  const issue = issues.find((i) => i.id === match.issueId);
  if (!issue) return { kind: "unreported" };
  if (match.kind === "changed") return { kind: "changed", issue };
  return issue.reportStatus === "발견" ? { kind: "unreported", issue } : { kind: "reported", issue };
}

export function MatchBadge({ match }: { match?: IssueMatch }) {
  const { issues } = useStore();
  const state = reportStateOf(match, issues);
  if (!state) return null;
  if (state.kind === "unreported" && !state.issue) {
    return <span className="badge report-no">미제보 · 기존 제보 없음</span>;
  }
  const issue = state.issue!;
  const text =
    state.kind === "unreported"
      ? `미제보 · ${issue.id} 등록만 함`
      : state.kind === "changed"
        ? `제보함 ${issue.id} · NH 설명과 달라짐`
        : `제보함 ${issue.id} · ${issue.reportStatus === "제보 완료" ? "답변 대기" : (issue.conclusion ?? "답변 받음")}`;
  return (
    <Link to={`/issues/${issue.id}`} className={`badge report-${state.kind === "unreported" ? "no" : state.kind}`}>
      {text}
    </Link>
  );
}

export function StatCard({
  label,
  value,
  tone,
  sub,
}: {
  label: string;
  value: number | string;
  tone?: RunStatus | "neutral" | "warn";
  sub?: React.ReactNode;
}) {
  return (
    <div className={`stat tone-${tone ?? "neutral"}`}>
      <div className="stat-label">{label}</div>
      <div className="stat-body">
        <div className="stat-value">{value}</div>
        {sub && <div className="stat-sub">{sub}</div>}
      </div>
    </div>
  );
}

// 원인별 건수. 많은 순으로 max개만 보여주고 나머지는 "외 N건"으로 줄인다
export function ReasonBreakdown({
  reasons,
  max = 2,
  order,
}: {
  reasons: (string | undefined)[];
  max?: number;
  order?: string[]; // 주면 이 순서를 따르고, 없으면 건수가 많은 순
}) {
  const counts = new Map<string, number>();
  for (const r of reasons) {
    const k = r ?? "원인 미분류";
    counts.set(k, (counts.get(k) ?? 0) + 1);
  }
  if (counts.size === 0) return null;
  const rank = (k: string) => (order?.includes(k) ? order.indexOf(k) : Infinity);
  const sorted = [...counts.entries()].sort((a, b) => (order ? rank(a[0]) - rank(b[0]) : 0) || b[1] - a[1]);
  const rest = sorted.slice(max).reduce((n, [, c]) => n + c, 0);
  return (
    <ul className="reasons">
      {sorted.slice(0, max).map(([k, n]) => (
        <li key={k}>
          <span>{k}</span>
          <span className="num">{n}</span>
        </li>
      ))}
      {rest > 0 && <li className="muted">외 {rest}건</li>}
    </ul>
  );
}

export function Code({ text, empty = "(빈 본문)" }: { text?: string; empty?: string }) {
  return <pre className="code">{text ? text : <span className="muted">{empty}</span>}</pre>;
}

export function PageHeader({ title, sub, actions }: { title: string; sub?: string; actions?: React.ReactNode }) {
  return (
    <div className="page-header">
      <div>
        <h1>{title}</h1>
        {sub && <p className="muted">{sub}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  );
}

export function fmtTime(iso: string) {
  const d = new Date(iso);
  const k = new Date(d.getTime() + 9 * 3600_000).toISOString();
  return `${k.slice(5, 10).replace("-", "/")} ${k.slice(11, 19)}`;
}

export function fmtDuration(ms: number) {
  if (ms === 0) return "-";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(ms < 10_000 ? 2 : 1)}s`;
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <div className="empty">{children}</div>;
}

// API 하나에 대해, 지금(최근 실행 기준) 실패 중인 케이스가 제보된 건지 센다
export function failReportCounts(apiId: string, latestByCase: Map<string, Run>, issues: Issue[]) {
  let unreported = 0;
  let reported = 0;
  for (const c of cases) {
    if (!c.apiIds.includes(apiId)) continue;
    const r = latestByCase.get(c.id);
    if (r?.status !== "fail") continue;
    const state = reportStateOf(r.match, issues);
    if (!state || state.kind === "unreported") unreported++;
    else reported++;
  }
  return { unreported, reported };
}

// full: 0건이어도 "제보 0 · 미제보 0" 으로 항상 보여준다
export function FailReportTag({ apiId, full }: { apiId: string; full?: boolean }) {
  const { issues, latestByCase } = useStore();
  const { unreported, reported } = failReportCounts(apiId, latestByCase, issues);
  if (!full && unreported + reported === 0) return null;
  return (
    <span className="row-inline">
      {(full || reported > 0) && <span className={`badge ${reported > 0 ? "report-reported" : "report-zero"}`}>제보 {reported}</span>}
      {(full || unreported > 0) && <span className={`badge ${unreported > 0 ? "report-no" : "report-zero"}`}>미제보 {unreported}</span>}
    </span>
  );
}

// 제보와 연결된 케이스에 자동으로 붙는 표시
export function RecheckTag({ caseId }: { caseId: string }) {
  const { caseIssue } = useStore();
  const issueId = caseIssue.get(caseId);
  if (!issueId) return null;
  return (
    <Link to={`/issues/${issueId}`} className="badge recheck" title="이 제보가 고쳐졌는지, 동작이 바뀌었는지 계속 확인하는 테스트">
      {issueId} 재확인
    </Link>
  );
}

// 테스트 목록의 제보 열: 모든 케이스에 제보 여부를 보여준다
// 실패 중이면 그 실패의 제보 상태, 실패가 아니어도 연결된 제보가 있으면 그 상태, 둘 다 아니면 "제보 대상 아님"
export function CaseReportBadge({ caseId, run }: { caseId: string; run?: Run }) {
  const { caseIssue } = useStore();
  if (run?.status === "fail" && run.match) return <MatchBadge match={run.match} />;
  const issueId = caseIssue.get(caseId);
  if (issueId) return <MatchBadge match={{ kind: "known", issueId }} />;
  return <span className="badge report-zero">제보 대상 아님</span>;
}
