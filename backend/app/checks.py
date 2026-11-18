"""판정 규칙 계산. 결과는 사람이 읽을 수 있는 기대값·실제값과 함께 남긴다."""

import re
from dataclasses import dataclass
from typing import Any

from app.cases import BlankCheck, Check, CountCheck, FieldCheck, RowsCheck
from app.expr import ExprError, as_number, evaluate, get_path


@dataclass
class Result:
    rule: str
    passed: bool
    expected: str
    actual: str

    def to_dict(self) -> dict[str, Any]:
        return {"rule": self.rule, "passed": self.passed, "expected": self.expected, "actual": self.actual}


@dataclass
class Context:
    status: int | None
    body: Any  # JSON이면 파싱한 값, 아니면 None
    text: str
    duration_ms: int
    row: dict[str, Any] | None = None  # select 로 고른 행
    rows: list[Any] | None = None  # paginate 로 모은 행


MISSING = object()


def short(v: Any, limit: int = 80) -> str:
    if v is MISSING:
        return "(없음)"
    if v is None:
        return "null"
    if isinstance(v, str):
        s = v if v != "" else '""'
    elif isinstance(v, (list, dict)):
        s = f"배열 {len(v)}개" if isinstance(v, list) else "객체"
    else:
        s = str(v)
    return s if len(s) <= limit else s[: limit - 1] + "…"


def resolve(ctx: Context, path: str) -> Any:
    try:
        if path == "rows":
            return ctx.rows if ctx.rows is not None else MISSING
        if path.startswith("row."):
            return get_path(ctx.row, path[4:]) if ctx.row is not None else MISSING
        if path == "row":
            return ctx.row if ctx.row is not None else MISSING
        return get_path(ctx.body, path)
    except (KeyError, IndexError, ValueError, TypeError):
        return MISSING


def _json_type(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, (int, float)):
        return "number"
    if isinstance(v, str):
        return "string"
    if isinstance(v, list):
        return "array"
    return "object"


def _num_or_expr(v: Any, names: dict[str, Any] | None = None) -> Any:
    if isinstance(v, str):
        try:
            return evaluate(v, names or {})
        except ExprError:
            return as_number(v)
    return v


def _same(a: Any, b: Any) -> bool:
    a2, b2 = as_number(a), as_number(b)
    if isinstance(a2, (int, float)) and isinstance(b2, (int, float)):
        return a2 == b2
    return str(a) == str(b)


def field_results(fc: FieldCheck, value: Any, label: str | None = None) -> list[Result]:
    name = label or fc.path
    if fc.note:
        name = f"{name} ({fc.note})"
    out: list[Result] = []
    shown = short(value)
    if fc.exists is not None:
        out.append(Result(f"{name} 있음" if fc.exists else f"{name} 없음", (value is not MISSING) == fc.exists, "있음" if fc.exists else "없음", "있음" if value is not MISSING else "없음"))
    if fc.type is not None:
        actual = "(없음)" if value is MISSING else _json_type(value)
        out.append(Result(f"{name} 타입", actual == fc.type, fc.type, f"{actual} {shown}" if value is not MISSING else actual))
    if fc.not_empty is not None:
        empty = value is MISSING or value in ("", None) or (isinstance(value, (list, dict)) and len(value) == 0)
        out.append(Result(f"{name} 비어있지 않음", (not empty) == fc.not_empty, "값 있음" if fc.not_empty else "빈 값", shown))
    if fc.eq is not None:
        out.append(Result(name, value is not MISSING and _same(value, fc.eq), short(fc.eq), shown))
    if fc.ne is not None:
        out.append(Result(name, value is MISSING or not _same(value, fc.ne), f"{short(fc.ne)} 아님", shown))
    if fc.in_ is not None:
        out.append(Result(name, value is not MISSING and any(_same(value, x) for x in fc.in_), " / ".join(short(x) for x in fc.in_) + " 중 하나", shown))
    if fc.regex is not None:
        out.append(Result(name, value is not MISSING and re.fullmatch(fc.regex, str(value)) is not None, f"형식 {fc.regex}", shown))
    for op, sym in (("gt", ">"), ("gte", "≥"), ("lt", "<"), ("lte", "≤")):
        bound = getattr(fc, op)
        if bound is None:
            continue
        b = _num_or_expr(bound)
        v = as_number(value) if value is not MISSING else MISSING
        ok = isinstance(v, (int, float)) and isinstance(b, (int, float)) and {
            "gt": v > b, "gte": v >= b, "lt": v < b, "lte": v <= b
        }[op]
        out.append(Result(name, ok, f"{sym} {short(b)}", shown))
    if not out:
        out.append(Result(f"{name} 있음", value is not MISSING, "있음", shown))
    return out


def _count(cc: CountCheck, ctx: Context, label: str | None) -> list[Result]:
    arr = resolve(ctx, cc.path)
    name = label or f"{cc.path} 건수"
    n = len(arr) if isinstance(arr, list) else None
    actual = f"{n}건" if n is not None else f"배열 아님 ({short(arr)})"
    out = []
    for op, sym in (("eq", "="), ("gte", "≥"), ("lte", "≤")):
        bound = getattr(cc, op)
        if bound is None:
            continue
        b = _num_or_expr(bound)
        ok = n is not None and isinstance(b, (int, float)) and {"eq": n == b, "gte": n >= b, "lte": n <= b}[op]
        out.append(Result(name, ok, f"{sym} {short(b)}건" if op != "eq" else f"{short(b)}건", actual))
    return out


def _no_rows(ctx: Context) -> bool:
    """NH는 조회 결과가 0건이면 배열 키(Occurs1)를 아예 빼고 nrec 를 0 으로 준다."""
    if not isinstance(ctx.body, dict) or "nrec" not in ctx.body:
        return False
    n = as_number(ctx.body.get("nrec"))
    return n == 0


def _rows(rc: RowsCheck, ctx: Context, label: str | None) -> Result:
    arr = resolve(ctx, rc.path)
    name = label or f"각 행: {rc.rule}" + (f" ({rc.when} 인 행)" if rc.when else "")
    if arr is MISSING and _no_rows(ctx):
        return Result(name, True, f"위반 {rc.max_violations}건 이하", "조회 결과 0건 (nrec 0)")
    if not isinstance(arr, list):
        return Result(name, False, "배열", short(arr))
    checked = 0
    bad: list[str] = []
    for i, row in enumerate(arr):
        if not isinstance(row, dict):
            continue
        try:
            if rc.when and not evaluate(rc.when, row):
                continue
            checked += 1
            if not evaluate(rc.rule, row):
                # 규칙과 조건에 쓴 필드를 보여준다. 날짜처럼 행을 알아볼 필드가 있으면 앞에 붙인다
                used = [k for k in row if re.search(rf"\b{re.escape(k)}\b", f"{rc.rule} {rc.when or ''}")]
                keys = [k for k in row if k.endswith(("_dt", "_ord_no")) and k not in used][:1] + used
                bad.append(f"{i + 1}행 " + ", ".join(f"{k}={row[k]}" for k in keys))
        except ExprError as e:
            checked += 1
            bad.append(f"{i + 1}행 계산 불가 ({e})")
    actual = f"위반 {len(bad)}건 / {checked}행"
    if bad:
        actual += f" (예: {bad[0]})"
    return Result(name, len(bad) <= rc.max_violations, f"위반 {rc.max_violations}건 이하", actual)


def _blank(bc: BlankCheck, ctx: Context, label: str | None) -> Result:
    arr = resolve(ctx, bc.path)
    name = label or "빈 행 아님"
    if not isinstance(arr, list):
        return Result(name, False, "배열", short(arr))
    blanks = 0
    for row in arr:
        if not isinstance(row, dict):
            continue
        keys = bc.fields or list(row.keys())
        if all(str(row.get(k) or "").strip() == "" for k in keys):
            blanks += 1
    actual = "빈 행 없음" if blanks == 0 else f"모든 필드가 빈 값인 행 {blanks}개 / {len(arr)}행"
    return Result(name, blanks == 0, "주요 필드 중 하나 이상 값 있음", actual)


def evaluate_check(check: Check, ctx: Context) -> list[Result]:
    label = check.name
    if check.status is not None:
        want = check.status
        got = ctx.status
        if isinstance(want, list):
            ok = got in want
            exp = " / ".join(str(w) for w in want)
        elif isinstance(want, str) and re.fullmatch(r"[1-5]xx", want):
            ok = got is not None and str(got)[0] == want[0]
            exp = f"{want[0]}00 계열"
        else:
            ok = got == int(want)
            exp = str(want)
        return [Result(label or "HTTP 상태", ok, exp, str(got))]
    if check.json_ is not None:
        is_json = isinstance(ctx.body, (dict, list))
        actual = "JSON" if is_json else ("빈 문자열" if ctx.text.strip() == "" else f"JSON 아님: {short(ctx.text, 40)}")
        return [Result(label or "본문이 JSON", is_json == check.json_, "JSON" if check.json_ else "JSON 아님", actual)]
    if check.error_code is not None:
        code = str(ctx.body.get("errorCode") or "").strip() if isinstance(ctx.body, dict) else ""
        if check.error_code.lower() == "none":
            return [Result(label or "오류 코드 없음", code == "", "없음", code or "없음")]
        return [Result(label or "errorCode", code == check.error_code, check.error_code, code or "없음")]
    if check.duration_ms is not None:
        return [Result(label or "응답 시간", ctx.duration_ms <= check.duration_ms.lte, f"≤ {check.duration_ms.lte:.0f}ms", f"{ctx.duration_ms}ms")]
    if check.field is not None:
        return field_results(check.field, resolve(ctx, check.field.path), label)
    if check.count is not None:
        return _count(check.count, ctx, label)
    if check.rows is not None:
        return [_rows(check.rows, ctx, label)]
    if check.rows_not_blank is not None:
        return [_blank(check.rows_not_blank, ctx, label)]
    return []
