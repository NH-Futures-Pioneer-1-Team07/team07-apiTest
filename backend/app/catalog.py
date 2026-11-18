"""API 목록. NH선물 API 명세를 읽어 내부 형식(`Api`)으로 바꾼다.

- 엑셀(전체_API_문서.xlsx): NH가 배포하는 원본. 있으면 이것을 쓴다
- 마크다운(docs/nh-api/apis/*.md): 엑셀을 옮겨 적은 문서

이후 Swagger 같은 다른 입력도 같은 `Api` 형식으로 바꿔서 쓰도록 한다.
"""

import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

Region = Literal["국내", "해외", "공통"]
Category = Literal["시세", "계좌", "주문", "인증", "실시간"]
# 호출 제한 등급. 주문 5건/초, 계좌·시세 10건/초
LimitKind = Literal["order", "account", "quote", "default", "realtime"]


class ApiField(BaseModel):
    parent: str = ""
    key: str
    name: str = ""
    type: str = ""
    length: str = ""
    description: str = ""
    required: bool = False
    defaultValue: str = ""


class Api(BaseModel):
    id: str
    name: str
    protocol: Literal["HTTP", "WS"]
    method: str
    contentType: str
    url: str
    demoDomain: str
    limit: str
    limitKind: LimitKind
    region: Region
    category: Category
    description: str
    input: list[ApiField]
    output: list[ApiField]
    requestExample: str
    responseExample: str

    @property
    def is_order(self) -> bool:
        return self.limitKind == "order"

    @property
    def market(self) -> Literal["domestic", "overseas"]:
        # 해외 API는 해외 전용 키로 불러야 한다
        return "overseas" if "/overseas/" in self.url else "domestic"


def _split_row(line: str) -> list[str]:
    cells = line.strip().removeprefix("|").removesuffix("|").split("|")
    return [c.strip().strip("`").replace("<br>", "\n") for c in cells]


def _sections(md: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {"_title": []}
    name = "_title"
    for line in md.splitlines():
        m = re.match(r"^## (.+)", line)
        if m:
            name = m.group(1).strip()
            out[name] = []
        else:
            out.setdefault(name, []).append(line)
    return out


def _table(lines: list[str] | None) -> list[dict[str, str]]:
    rows = [l for l in (lines or []) if l.strip().startswith("|")]
    if len(rows) < 2:
        return []
    head = _split_row(rows[0])
    result = []
    for r in rows[2:]:
        cells = _split_row(r)
        result.append({h: (cells[i] if i < len(cells) else "") for i, h in enumerate(head)})
    return result


def _code_block(lines: list[str] | None) -> str:
    text = "\n".join(lines or [])
    m = re.search(r"```[a-z]*\n([\s\S]*?)```", text)
    return (m.group(1) if m else text).strip()


def _limit_kind(info: dict[str, str]) -> LimitKind:
    limit = info.get("API 요청 제한", "")
    if info.get("API 통신 방식") == "WEBSOCKET":
        return "realtime"
    if "주문" in limit:
        return "order"
    if "계좌" in limit:
        return "account"
    if "시세" in limit:
        return "quote"
    return "default"


CATEGORY: dict[LimitKind, Category] = {
    "order": "주문",
    "account": "계좌",
    "quote": "시세",
    "default": "인증",
    "realtime": "실시간",
}


def _region(doc_id: str) -> Region:
    if doc_id.startswith("domestic") or re.fullmatch(r"K[A-D]", doc_id) or doc_id == "O1_K":
        return "국내"
    if doc_id.startswith("overseas") or re.fullmatch(r"F[AB]", doc_id) or doc_id == "O1":
        return "해외"
    return "공통"


def parse_api(doc_id: str, md: str) -> Api:
    s = _sections(md)
    info = {r.get("항목", ""): r.get("값", "") for r in _table(s.get("기본 정보"))}
    return _build(
        doc_id,
        info,
        description=_code_block(s.get("설명")),
        inputs=_table(s.get("INPUT")),
        outputs=_table(s.get("OUTPUT")),
        request=_code_block(s.get("Request JSON (Input)")),
        response=_code_block(s.get("Response JSON (Output)")),
    )


def _build(
    doc_id: str,
    info: dict[str, str],
    description: str,
    inputs: list[dict[str, str]],
    outputs: list[dict[str, str]],
    request: str,
    response: str,
) -> Api:
    kind = _limit_kind(info)
    return Api(
        id=doc_id,
        name=info.get("API 명") or doc_id,
        protocol="WS" if info.get("API 통신 방식") == "WEBSOCKET" else "HTTP",
        method=info.get("HTTP Method", ""),
        contentType=info.get("Content-Type", ""),
        url=info.get("URL 명", ""),
        demoDomain=info.get("모의 Domain", ""),
        limit=info.get("API 요청 제한", ""),
        limitKind=kind,
        region=_region(doc_id),
        category=CATEGORY[kind],
        description=description,
        input=[
            ApiField(
                parent=r.get("상위 Object", ""),
                key=r.get("Key", ""),
                name=r.get("한글명", ""),
                type=r.get("Type", ""),
                length=r.get("길이", ""),
                description=r.get("설명", ""),
                required=r.get("필수") == "Y",
                defaultValue=r.get("기본값", ""),
            )
            for r in inputs
        ],
        output=[
            ApiField(
                parent=r.get("상위 Object", ""),
                key=r.get("Key", ""),
                name=r.get("한글명", ""),
                type=r.get("Type", ""),
                length=r.get("길이", ""),
                description=r.get("설명", ""),
            )
            for r in outputs
        ],
        requestExample=request,
        responseExample=response,
    )


def _pretty_json(text: str) -> str:
    try:
        return json.dumps(json.loads(text), ensure_ascii=False, indent=2)
    except (ValueError, TypeError):
        return text


def load_catalog_xlsx(path: Path) -> list[Api]:
    """NH 엑셀 명세. 'API 목록' 시트를 뺀 시트 하나가 API 하나이고, 시트 이름이 문서명(id)이다."""
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    apis = []
    sections = ("INPUT", "OUTPUT", "Request JSON (Input)", "Response JSON (Output)")
    for name in wb.sheetnames:
        if name == "API 목록":
            continue
        rows = [["" if c is None else str(c).strip() for c in r] for r in wb[name].iter_rows(values_only=True)]
        info: dict[str, str] = {}
        parts: dict[str, list[list[str]]] = {}
        current: str | None = None
        for r in rows:
            first = r[0] if r else ""
            if first in sections:
                current = first
                parts[current] = []
                continue
            if current is None:
                if len(r) > 1 and first:
                    info[first] = r[1]
            elif any(r):
                parts[current].append(r)

        def table(key: str) -> list[dict[str, str]]:
            t = parts.get(key, [])
            if not t:
                return []
            head = t[0]
            return [{h: (row[i] if i < len(row) else "") for i, h in enumerate(head) if h} for row in t[1:]]

        def text(key: str) -> str:
            return _pretty_json(" ".join(r[0] for r in parts.get(key, []) if r and r[0]))

        apis.append(
            _build(
                name,
                info,
                description=info.get("설명", ""),
                inputs=table("INPUT"),
                outputs=table("OUTPUT"),
                request=text("Request JSON (Input)"),
                response=text("Response JSON (Output)"),
            )
        )
    return apis


def load_catalog(docs_dir: Path) -> list[Api]:
    """명세 폴더에 엑셀이 있으면 엑셀을, 없으면 마크다운을 README 목록 순서대로 읽는다."""
    # 오류코드 정의서 같은 다른 엑셀이 같은 폴더에 있을 수 있어서 이름에 API 가 들어간 파일만 본다
    xlsx = sorted(p for p in docs_dir.glob("*.xlsx") if "API" in p.name.upper())
    if xlsx:
        return load_catalog_xlsx(xlsx[0])
    apis_dir = docs_dir / "apis"
    if not apis_dir.is_dir():
        raise FileNotFoundError(f"API 문서 폴더가 없습니다: {apis_dir} (NH_DOCS_DIR 설정 확인)")
    readme = docs_dir / "README.md"
    order = re.findall(r"\(apis/([^)]+)\.md\)", readme.read_text("utf-8")) if readme.exists() else []
    files = sorted(p.stem for p in apis_dir.glob("*.md"))
    ids = list(dict.fromkeys([*order, *files]))
    return [parse_api(i, (apis_dir / f"{i}.md").read_text("utf-8")) for i in ids if (apis_dir / f"{i}.md").exists()]
