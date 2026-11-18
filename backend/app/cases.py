"""테스트 케이스 파일(YAML) 형식, 읽기, 검증.

케이스 하나는 파일 하나다. 형식 예시는 testcases/README.md 를 본다.
"""

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.catalog import Api
from app.expr import ExprError, evaluate, referenced_vars

Condition = Literal["국내 주간장", "국내 야간장", "국내 장외", "CME 열림", "모의 해외 주문 가능"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class FieldCheck(Strict):
    """경로의 값 하나를 검사한다. 여러 조건을 주면 모두 맞아야 한다."""

    path: str
    eq: Any = None
    ne: Any = None
    in_: list[Any] | None = Field(default=None, alias="in")
    regex: str | None = None
    not_empty: bool | None = None
    exists: bool | None = None
    type: Literal["string", "number", "boolean", "array", "object", "null"] | None = None
    gt: Any = None
    gte: Any = None
    lt: Any = None
    lte: Any = None
    note: str | None = None


class CountCheck(Strict):
    """배열 길이. `eq: "min(${req_qty}, 2000)"` 처럼 식을 쓸 수 있다."""

    path: str
    eq: Any = None
    gte: Any = None
    lte: Any = None


class RowsCheck(Strict):
    """배열의 모든 행에 식을 적용한다. 식에는 행의 필드 이름을 그대로 쓴다."""

    path: str
    rule: str
    when: str | None = None  # 이 식이 참인 행에만 적용
    max_violations: int = 0


class BlankCheck(Strict):
    """HTTP 200인데 행의 주요 필드가 모두 빈 값인지. fields 를 생략하면 모든 필드를 본다."""

    path: str
    fields: list[str] | None = None


class Bound(Strict):
    lte: float


class Check(Strict):
    """판정 규칙 하나. 아래 키 중 하나만 쓴다."""

    name: str | None = None
    status: int | str | list[int] | None = None  # 200, "4xx", [400, 404]
    json_: bool | None = Field(default=None, alias="json")
    field: FieldCheck | None = None
    count: CountCheck | None = None
    rows: RowsCheck | None = None
    rows_not_blank: BlankCheck | None = None
    error_code: str | None = None  # 응답 errorCode. "none" 이면 오류 코드가 없어야 함
    duration_ms: Bound | None = None

    @model_validator(mode="after")
    def one_kind(self) -> "Check":
        kinds = [k for k in ("status", "json_", "field", "count", "rows", "rows_not_blank", "error_code", "duration_ms") if getattr(self, k) is not None]
        if len(kinds) != 1:
            raise ValueError("판정 규칙에는 status, json, field, count, rows, rows_not_blank, error_code, duration_ms 중 하나만 씁니다")
        return self


class Extract(Strict):
    path: str
    expr: str | None = None  # value 라는 이름으로 값을 받아 계산. 예: "floor(value * 0.98 * 100) / 100"
    format: str | None = None  # 예: "{:.2f}"


class Select(Strict):
    """배열에서 행 하나를 고른다. 고른 행은 `row.필드` 로 쓴다."""

    path: str
    where: dict[str, Any]


class Paginate(Strict):
    """다음 키를 따라 마지막 페이지까지 받는다."""

    next_key: str = "nxt_key"  # 응답에서 꺼내 다음 요청 같은 이름에 넣는다
    rows: str = "Occurs1"
    max_pages: int = 50
    expect_all: list[Check] = []  # 모든 페이지의 행을 합쳐서 검사 (rows/count 의 path 는 "rows")


class WaitUntil(FieldCheck):
    """조건이 맞을 때까지 같은 요청을 반복한다."""

    interval_s: float = 1.0
    timeout_s: float = 60.0


class Step(Strict):
    name: str
    api: str
    body: dict[str, Any] | None = None
    each: list[dict[str, Any]] | None = None  # 값마다 body 에 덮어써서 한 번씩 부른다
    extract: dict[str, str | Extract] = {}
    select: Select | None = None
    wait_until: WaitUntil | None = None
    paginate: Paginate | None = None
    expect: list[Check] = []
    timeout_s: float = 30.0
    auth: bool = True  # false 면 Authorization 헤더 없이 보낸다
    market: Literal["domestic", "overseas"] | None = None  # 토큰 발급 단계에서 어느 키를 쓸지
    if_failed: bool = False  # 정리 단계 전용: 앞 단계가 실패·오류였을 때만 실행


class Case(Strict):
    id: str
    name: str
    description: str = ""
    tags: list[str] = []
    issue: str | None = None  # 이 케이스가 재확인하는 제보
    issue_result: Literal["fail", "success"] = "fail"  # 제보한 문제가 그대로일 때의 결과
    when: list[Condition] = []  # 모두 맞을 때만 실행. 아니면 건너뜀
    steps: list[Step]
    cleanup: list[Step] = []  # 결과와 관계없이 마지막에 실행
    path: str = Field(default="", exclude=True)

    def api_ids(self) -> list[str]:
        return list(dict.fromkeys(s.api for s in [*self.steps, *self.cleanup]))

    def kind(self) -> Literal["단일", "시나리오"]:
        real = [a for a in self.api_ids() if a != "token"]
        return "시나리오" if len(real) > 1 else "단일"


class CaseFileError(Exception):
    def __init__(self, path: Path, problems: list[str]):
        super().__init__(f"{path.name}: " + "; ".join(problems))
        self.path = path
        self.problems = problems


def load_cases(cases_dir: Path) -> tuple[list[Case], list[CaseFileError]]:
    cases: list[Case] = []
    errors: list[CaseFileError] = []
    for p in sorted(cases_dir.glob("*.y*ml")):
        try:
            data = yaml.safe_load(p.read_text("utf-8"))
            case = Case.model_validate(data)
            case.path = str(p)
            cases.append(case)
        except (yaml.YAMLError, ValidationError) as e:
            problems = (
                [f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors()]
                if isinstance(e, ValidationError)
                else [str(e)]
            )
            errors.append(CaseFileError(p, problems))
    return cases, errors


def validate_case(case: Case, apis: dict[str, Api]) -> list[str]:
    """실행 전에 잡을 수 있는 문제: 없는 API, 명세에 없는 요청 필드, 정의되지 않은 변수."""
    problems: list[str] = []
    defined: set[str] = set()
    for step in [*case.steps, *case.cleanup]:
        api = apis.get(step.api)
        where = f"[{step.name}]"
        if api is None:
            problems.append(f"{where} 없는 API: {step.api}")
            continue
        if api.protocol == "WS":
            problems.append(f"{where} WebSocket API는 아직 실행할 수 없습니다: {step.api}")
        known = {f.key for f in api.input}
        body_keys = set((step.body or {}).keys())
        for e in step.each or []:
            body_keys |= set(e.keys())
        if step.api != "token":
            for k in body_keys - known:
                problems.append(f"{where} 명세에 없는 요청 필드: {k}")
        each_vars = set().union(*(set(e.keys()) for e in step.each)) if step.each else set()
        scope = defined | each_vars
        used = referenced_vars(step.body) | referenced_vars([c.model_dump(by_alias=True) for c in step.expect])
        if step.select:
            used |= referenced_vars(step.select.where)
        for v in sorted(used - scope):
            problems.append(f"{where} 정의되지 않은 변수: ${{{v}}}")
        for c in step.expect:
            if c.rows:
                try:
                    evaluate(c.rows.rule.replace("${", "_").replace("}", ""), _AnyNames())
                except ExprError as e:
                    if "알 수 없는 이름" not in str(e):
                        problems.append(f"{where} 식 오류: {e}")
        defined |= set(step.extract.keys())
    return problems


class _AnyNames(dict):
    """식 문법만 검사할 때 모든 이름을 1로 본다."""

    def __contains__(self, key: object) -> bool:
        return True

    def __getitem__(self, key: str) -> int:
        return 1
