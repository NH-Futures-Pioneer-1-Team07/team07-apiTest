"""케이스 파일에서 쓰는 변수 치환과 간단한 식 계산.

- `${이름}`: 앞 단계에서 꺼낸 변수나 `each` 값으로 바꾼다
- 기본 변수: `${today}`(YYYYMMDD, 한국 시간), `${days_ago:60}`
- 식: `min(${req_qty}, 2000)`, `occurs1_low_pric <= occurs1_open_pric <= occurs1_high_pric`
  숫자처럼 생긴 문자열은 숫자로 바꿔서 비교한다. 함수는 min, max, abs, round, floor, ceil, len 만 쓸 수 있다.
"""

import ast
import math
import operator
import re
from datetime import datetime, timedelta, timezone
from typing import Any

KST = timezone(timedelta(hours=9))
VAR = re.compile(r"\$\{([^}]+)\}")


class ExprError(ValueError):
    pass


def _builtin(name: str, now: datetime) -> str | None:
    if name == "today":
        return now.strftime("%Y%m%d")
    if name.startswith("days_ago:"):
        return (now - timedelta(days=int(name.split(":", 1)[1]))).strftime("%Y%m%d")
    return None


def render(value: Any, variables: dict[str, Any], now: datetime | None = None) -> Any:
    """값 안의 `${이름}`을 바꾼다. 사전·목록은 안쪽까지 바꾼다."""
    now = now or datetime.now(KST)
    if isinstance(value, dict):
        return {k: render(v, variables, now) for k, v in value.items()}
    if isinstance(value, list):
        return [render(v, variables, now) for v in value]
    if not isinstance(value, str):
        return value

    def sub(m: re.Match[str]) -> str:
        name = m.group(1).strip()
        if name in variables:
            return str(variables[name])
        b = _builtin(name, now)
        if b is None:
            raise ExprError(f"정의되지 않은 변수: ${{{name}}}")
        return b

    return VAR.sub(sub, value)


def referenced_vars(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set().union(*(referenced_vars(v) for v in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(referenced_vars(v) for v in value)) if value else set()
    if isinstance(value, str):
        return {n.strip() for n in VAR.findall(value) if not n.startswith(("today", "days_ago:"))}
    return set()


def as_number(v: Any) -> Any:
    if isinstance(v, str):
        t = v.strip()
        if re.fullmatch(r"[+-]?\d+(\.\d+)?", t):
            return float(t) if "." in t else int(t)
    return v


_BIN = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
}
_CMP = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}
_FUNCS = {"min": min, "max": max, "abs": abs, "round": round, "floor": math.floor, "ceil": math.ceil, "len": len}


def evaluate(expr: str, names: dict[str, Any] | None = None) -> Any:
    names = names or {}
    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError as e:
        raise ExprError(f"식을 읽을 수 없습니다: {expr}") from e

    def ev(node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant):
            return as_number(node.value)
        if isinstance(node, ast.Name):
            if node.id not in names:
                raise ExprError(f"알 수 없는 이름: {node.id}")
            return as_number(names[node.id])
        if isinstance(node, (ast.List, ast.Tuple)):
            return [ev(e) for e in node.elts]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd, ast.Not)):
            v = ev(node.operand)
            return -v if isinstance(node.op, ast.USub) else (v if isinstance(node.op, ast.UAdd) else not v)
        if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
            return _BIN[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.BoolOp):
            vals = [ev(v) for v in node.values]
            return all(vals) if isinstance(node.op, ast.And) else any(vals)
        if isinstance(node, ast.Compare):
            left = ev(node.left)
            for op, comp in zip(node.ops, node.comparators):
                right = ev(comp)
                if type(op) not in _CMP or not _CMP[type(op)](left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS:
            return _FUNCS[node.func.id](*[ev(a) for a in node.args])
        raise ExprError(f"쓸 수 없는 식입니다: {ast.unparse(node)}")

    try:
        return ev(tree)
    except ExprError:
        raise
    except Exception as e:  # 0으로 나누기, 문자열과 숫자 비교 등
        raise ExprError(f"식을 계산할 수 없습니다: {expr} ({type(e).__name__})") from e


def get_path(data: Any, path: str) -> Any:
    """`Occurs1.0.occurs1_sym` 처럼 점으로 이은 경로의 값. 없으면 KeyError."""
    cur = data
    for part in path.split("."):
        if part == "":
            continue
        if isinstance(cur, list):
            cur = cur[int(part)]
        elif isinstance(cur, dict):
            if part not in cur:
                raise KeyError(path)
            cur = cur[part]
        else:
            raise KeyError(path)
    return cur
