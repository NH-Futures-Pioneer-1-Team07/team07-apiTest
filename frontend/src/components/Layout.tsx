import { NavLink, Outlet } from "react-router-dom";
import { useStore } from "../store";

export function Layout() {
  const { issues, latestByCase, status } = useStore();
  const newFails = [...latestByCase.values()].filter((r) => r.status === "fail" && r.match?.kind === "new").length;
  const found = issues.filter((i) => i.reportStatus === "발견").length;

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">◆</span>
          <div>
            <div className="brand-name">API 테스트 콘솔</div>
            <div className="brand-project">NH선물 · {status?.env === "real" ? "실전" : "모의"}</div>
          </div>
        </div>
        <nav>
          <NavLink to="/" end>대시보드</NavLink>
          <NavLink to="/apis">API 목록</NavLink>
          <NavLink to="/tests">
            테스트 목록
            {newFails > 0 && <span className="nav-count">{newFails}</span>}
          </NavLink>
          <NavLink to="/issues">
            제보 내역
            {found > 0 && <span className="nav-count">{found}</span>}
          </NavLink>
        </nav>
        <div className="sidebar-foot muted">
          대상: {status?.baseUrl.replace("https://", "")}
          <br />
          {status?.env === "real" ? "실전 · 주문 케이스 차단" : "모의 환경"}
        </div>
      </aside>
      <main className="main">
        <StatusBanner />
        <Outlet />
      </main>
    </div>
  );
}

// 키가 없거나 케이스 파일에 문제가 있으면 화면 위에 알린다
function StatusBanner() {
  const { status } = useStore();
  if (!status) return null;
  const notes: string[] = [];
  if (!status.domesticKey) notes.push("국내 API 키(NH_APP_KEY, NH_APP_SECRET)가 없습니다");
  if (!status.overseasKey) notes.push("해외 API 키(NH_OVERSEAS_APP_KEY, NH_OVERSEAS_APP_SECRET)가 없습니다");
  for (const p of status.caseProblems) notes.push(`케이스 파일 ${p.file}: ${p.problems.join("; ")}`);
  if (notes.length === 0) return null;
  return (
    <div className="sample-banner">
      {notes.map((n) => (
        <div key={n}>{n}</div>
      ))}
      {(!status.domesticKey || !status.overseasKey) && <div>backend/.env 에 키를 넣고 백엔드를 다시 시작하세요.</div>}
    </div>
  );
}
