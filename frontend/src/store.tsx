import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { Api, Issue, ReportStatus, Run, ServerStatus, TestCase } from "./data/types";

// API 목록과 케이스는 처음 한 번 받아서 여기에 채운다. 화면 여러 곳에서 import 해서 쓴다.
export const apis: Api[] = [];
export const cases: TestCase[] = [];
export const apiById = new Map<string, Api>();
export const caseById = new Map<string, TestCase>();

type Store = {
  status: ServerStatus | null;
  runs: Run[];
  issues: Issue[];
  latestByCase: Map<string, Run>;
  caseIssue: Map<string, string>; // 케이스 id → 재확인하는 제보 id
  runCases: (caseIds: string[]) => Promise<void>;
  runCase: (caseId: string) => Promise<void>;
  loadRun: (runId: string) => Promise<Run>;
  setReportStatus: (issueId: string, status: ReportStatus) => Promise<void>;
  registerIssue: (run: Run) => Promise<string>;
  reloadCases: () => Promise<void>;
};

const Ctx = createContext<Store | null>(null);

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
  });
  if (!res.ok) {
    let detail = "";
    try {
      detail = (await res.json()).detail ?? "";
    } catch {
      detail = res.statusText;
    }
    throw new Error(`${path}: ${res.status} ${detail}`);
  }
  return res.json() as Promise<T>;
}

function fill<T extends { id: string }>(arr: T[], map: Map<string, T>, items: T[]) {
  arr.splice(0, arr.length, ...items);
  map.clear();
  for (const x of items) map.set(x.id, x);
}

export function StoreProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [status, setStatus] = useState<ServerStatus | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [caseVersion, setCaseVersion] = useState(0);

  const upsertRun = useCallback((run: Run) => {
    setRuns((rs) => {
      const i = rs.findIndex((r) => r.id === run.id);
      if (i < 0) return [...rs, run];
      const next = rs.slice();
      next[i] = run;
      return next;
    });
  }, []);

  const upsertIssue = useCallback((issue: Issue) => {
    setIssues((is) => {
      const i = is.findIndex((x) => x.id === issue.id);
      if (i < 0) return [...is, issue];
      const next = is.slice();
      next[i] = issue;
      return next;
    });
  }, []);

  const reloadCases = useCallback(async () => {
    fill(cases, caseById, await api<TestCase[]>("/api/cases"));
    setCaseVersion((v) => v + 1);
  }, []);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [a, c, r, i, s] = await Promise.all([
          api<Api[]>("/api/apis"),
          api<TestCase[]>("/api/cases"),
          api<Run[]>("/api/runs"),
          api<Issue[]>("/api/issues"),
          api<ServerStatus>("/api/status"),
        ]);
        if (!alive) return;
        fill(apis, apiById, a);
        fill(cases, caseById, c);
        setRuns(r);
        setIssues(i);
        setStatus(s);
        setReady(true);
      } catch (e) {
        if (alive) setLoadError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  // 실행 상태가 바뀌면 서버가 알려준다
  useEffect(() => {
    if (!ready) return;
    const es = new EventSource("/api/events");
    es.addEventListener("run", (e) => upsertRun(JSON.parse((e as MessageEvent).data)));
    es.addEventListener("issue", (e) => {
      upsertIssue(JSON.parse((e as MessageEvent).data));
      reloadCases();
    });
    return () => es.close();
  }, [ready, upsertRun, upsertIssue, reloadCases]);

  const latestByCase = useMemo(() => {
    const m = new Map<string, Run>();
    for (const r of runs) {
      const prev = m.get(r.caseId);
      if (!prev || r.startedAt > prev.startedAt) m.set(r.caseId, r);
    }
    return m;
  }, [runs]);

  const caseIssue = useMemo(() => {
    const m = new Map<string, string>();
    for (const c of cases) if (c.issueId) m.set(c.id, c.issueId);
    return m;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseVersion, ready]);

  const runCases = useCallback(async (caseIds: string[]) => {
    if (caseIds.length === 0) return;
    await api("/api/runs", { method: "POST", body: JSON.stringify({ caseIds }) });
  }, []);

  const runCase = useCallback((caseId: string) => runCases([caseId]), [runCases]);

  const loadRun = useCallback(
    async (runId: string) => {
      const run = await api<Run>(`/api/runs/${runId}`);
      upsertRun(run);
      return run;
    },
    [upsertRun],
  );

  const setReportStatus = useCallback(
    async (issueId: string, reportStatus: ReportStatus) => {
      upsertIssue(await api<Issue>(`/api/issues/${issueId}`, { method: "PATCH", body: JSON.stringify({ reportStatus }) }));
    },
    [upsertIssue],
  );

  const registerIssue = useCallback(
    async (run: Run) => {
      const issue = await api<Issue>("/api/issues", { method: "POST", body: JSON.stringify({ runId: run.id }) });
      upsertIssue(issue);
      await reloadCases();
      return issue.id;
    },
    [upsertIssue, reloadCases],
  );

  const value = useMemo(
    () => ({ status, runs, issues, latestByCase, caseIssue, runCases, runCase, loadRun, setReportStatus, registerIssue, reloadCases }),
    [status, runs, issues, latestByCase, caseIssue, runCases, runCase, loadRun, setReportStatus, registerIssue, reloadCases],
  );

  if (loadError) {
    return (
      <div className="boot">
        <h1>백엔드에 연결할 수 없습니다</h1>
        <p className="muted">{loadError}</p>
        <pre className="code">cd backend && uv run uvicorn app.main:create_app --factory --reload --timeout-graceful-shutdown 2</pre>
      </div>
    );
  }
  if (!ready) return <div className="boot muted">불러오는 중…</div>;
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useStore() {
  const s = useContext(Ctx);
  if (!s) throw new Error("StoreProvider 밖에서 사용");
  return s;
}
