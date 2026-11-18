export type ApiField = {
  parent: string;
  key: string;
  name: string;
  type: string;
  length: string;
  description: string;
  required?: boolean;
  defaultValue?: string;
};

export type Api = {
  id: string;
  name: string;
  protocol: "HTTP" | "WS";
  method: string;
  contentType: string;
  url: string;
  demoDomain: string;
  limit: string;
  limitKind: "order" | "account" | "quote" | "default" | "realtime";
  region: "국내" | "해외" | "공통";
  category: "시세" | "계좌" | "주문" | "인증" | "실시간";
  description: string;
  input: ApiField[];
  output: ApiField[];
  requestExample: string;
  responseExample: string;
};

export type RunStatus = "success" | "fail" | "running" | "error" | "skipped";

export type MarketState = "주간" | "야간" | "장외";

// 테스트가 실행되지 못한 원인
export type ErrorKind = "연결 실패" | "인증 설정 누락" | "인증 실패" | "케이스 파일 오류" | "기준 데이터 없음";
// 케이스 전체를 일부러 실행하지 않은 원인 (시나리오 안 단계 건너뜀은 포함하지 않음)
export type SkipKind = "시간대 조건 밖" | "휴장일" | "실전 차단";

export type Assertion = {
  rule: string;
  passed: boolean;
  expected: string;
  actual: string;
};

export type StepRun = {
  name: string;
  apiId: string;
  status: RunStatus;
  durationMs: number;
  request?: { method: string; url: string; headers: Record<string, string>; body: string };
  response?: { status: number; headers: Record<string, string>; body: string } | null;
  assertions: Assertion[];
  extracted?: Record<string, string>;
  note?: string;
  superseded?: boolean; // 규칙에 따라 다시 보내기 전의 시도. 결과 판정에는 쓰지 않는다
};

export type IssueMatch =
  | { kind: "new" }
  | { kind: "known"; issueId: string }
  | { kind: "changed"; issueId: string };

export type Run = {
  id: string;
  caseId: string;
  status: RunStatus;
  startedAt: string; // ISO
  durationMs: number;
  env: "모의" | "실전";
  market: MarketState;
  failure?: { expected: string; actual: string; reason: string };
  skipKind?: SkipKind;
  skipReason?: string;
  errorKind?: ErrorKind;
  errorReason?: string;
  match?: IssueMatch;
  steps: StepRun[];
  stepsOmitted?: boolean; // 목록에서는 최근 실행만 단계 원문이 온다
};

export type TestCase = {
  id: string;
  name: string;
  kind: "단일" | "시나리오";
  apiIds: string[];
  tags: string[];
  issueId?: string | null; // 이 케이스가 재확인하는 제보. 연결되면 화면에 "NH-00X 재확인"이 자동으로 붙는다
  description: string;
  when?: string[];
  file?: string;
};

export type ReportStatus = "발견" | "제보 완료" | "답변 받음";

export type Conclusion =
  | "명세 수정 예정"
  | "명세 수정 완료"
  | "의도된 동작"
  | "모의 환경 한정"
  | "NH 확인 중";

export type Issue = {
  id: string;
  title: string;
  apiIds: string[];
  team: string;
  firstSeen: string;
  reportedAt?: string;
  answeredAt?: string;
  reportStatus: ReportStatus;
  conclusion?: Conclusion;
  symptom: string;
  nhAnswer?: string;
  rules: string[];
  pending: string[];
  cases?: string[];
};

export type ServerStatus = {
  env: "mock" | "real";
  baseUrl: string;
  domesticKey: boolean;
  overseasKey: boolean;
  apiCount: number;
  caseProblems: { file: string; caseId?: string; problems: string[] }[];
  queued: number;
};
