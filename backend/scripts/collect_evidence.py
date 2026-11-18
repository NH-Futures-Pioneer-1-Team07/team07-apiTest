"""제보 증거 모으기. 재현 요청을 다시 보내고 요청·응답 원문을 issues/nh-futures/evidence/<제보ID>/ 에 남긴다.

uv run python scripts/collect_evidence.py NH-014 NH-015 NH-016

- 토큰·키·계좌번호는 가려서 저장한다.
- 페이지를 넘기는 요청은 1페이지 원문과 전체 페이지 요약(페이지별 nxt_key, 봉 수, 날짜 범위)을 남긴다.
- 조회 API만 쓴다. 주문은 보내지 않는다.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.catalog import load_catalog  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.market import KST  # noqa: E402
from app.nh import Exchange, NHClient, mask  # noqa: E402

ZN = {"exch_cd": "FCME", "sym": "ZNZ26", "req_qty": "2000", "nxt_key": "99999999"}
ZN_5M = {**ZN, "dcnt": "5", "cidx_yn": "0"}
KTB = {"nght_tp": "1", "sym": "A676C000"}
KTB_5M_1117 = {**KTB, "inq_strt_dt": "20261117", "strt_tm": "000000", "inq_ed_dt": "20261117", "ed_tm": "235959", "req_qty": "2000", "dcnt": "5", "cidx_yn": "0"}
KTB_5M_WIDE = {**KTB_5M_1117, "inq_strt_dt": "20260901", "inq_ed_dt": "20261118"}
KTB_D_1102 ={**KTB, "inq_strt_dt": "20261102", "inq_ed_dt": "20261113", "req_qty": "999", "cidx_yn": "0"}

# 제보별 재현 요청: (파일 이름, 설명, API, 본문, 끝까지 페이지 넘김)
PLANS: dict[str, list[tuple[str, str, str, dict[str, Any], bool]]] = {
    "NH-014": [
        ("01_daily_start-1101_end-default", "해외 일봉, 시작 20261101, 종료 기본값 → 시작일 무시", "overseas_chart-daily", {**ZN, "cidx_yn": "0", "inq_strt_dt": "20261101", "inq_ed_dt": "99999999"}, False),
        ("02_daily_start-1101_end-1231", "해외 일봉, 시작 20261101, 종료 20261231 → 시작일 적용", "overseas_chart-daily", {**ZN, "cidx_yn": "0", "inq_strt_dt": "20261101", "inq_ed_dt": "20261231"}, False),
        ("03_linked-daily_start-20230112_end-default_all-pages", "해외 연결 일봉, 시작 20230112, 종료 기본값, 끝까지", "overseas_chart-daily", {**ZN, "cidx_yn": "1", "inq_strt_dt": "20230112", "inq_ed_dt": "99999999"}, True),
        ("04_5min_start-1117_end-default_all-pages", "해외 5분봉, 시작 20261117 000000, 종료 기본값, 끝까지", "overseas_chart-minute", {**ZN_5M, "inq_strt_dt": "20261117", "strt_tm": "000000", "inq_ed_dt": "99999999", "ed_tm": "235959"}, True),
        ("05_5min_start-1117_end-1119_all-pages", "해외 5분봉, 시작 20261117 000000, 종료 20261119 235959, 끝까지", "overseas_chart-minute", {**ZN_5M, "inq_strt_dt": "20261117", "strt_tm": "000000", "inq_ed_dt": "20261119", "ed_tm": "235959"}, True),
        ("06_compare_domestic-daily_start-1101_end-default", "비교: 국내 일봉, 시작 20261101, 종료 기본값 → 시작일 적용", "domestic_chart-daily", {**KTB, "cidx_yn": "0", "req_qty": "300", "inq_strt_dt": "20261101", "inq_ed_dt": "99999999"}, False),
    ],
    "NH-015": [
        (f"{i + 1:02d}_req-qty-{q}", f"국내 연결 일봉 req_qty {q}", "domestic_chart-daily", {**KTB, "cidx_yn": "1", "req_qty": q}, False)
        for i, q in enumerate(["999", "1000", "1194", "1200", "1500", "2000", "3000"])
    ],
    "NH-016": [
        ("01_daily_start-1101_end-1231", "해외 일봉, 시작 20261101, 종료 20261231", "overseas_chart-daily", {**ZN, "cidx_yn": "0", "inq_strt_dt": "20261101", "inq_ed_dt": "20261231"}, False),
        ("02_daily_start-1101_end-1110", "해외 일봉, 시작 20261101, 종료 20261110 → 11-10 이후 봉이 옴", "overseas_chart-daily", {**ZN, "cidx_yn": "0", "inq_strt_dt": "20261101", "inq_ed_dt": "20261110"}, False),
        ("03_daily_start-default_end-1110", "해외 일봉, 시작 기본값, 종료 20261110", "overseas_chart-daily", {**ZN, "cidx_yn": "0", "inq_strt_dt": "00000000", "inq_ed_dt": "20261110"}, False),
        ("04_5min_1117-000000_to_1119-235959_all-pages", "해외 5분봉, 20261117 000000 ~ 20261119 235959, 끝까지", "overseas_chart-minute", {**ZN_5M, "inq_strt_dt": "20261117", "strt_tm": "000000", "inq_ed_dt": "20261119", "ed_tm": "235959"}, True),
        ("05_5min_1117-000000_to_1117-235959_all-pages", "해외 5분봉, 20261117 하루, 끝까지 → 11-18·19 봉이 옴", "overseas_chart-minute", {**ZN_5M, "inq_strt_dt": "20261117", "strt_tm": "000000", "inq_ed_dt": "20261117", "ed_tm": "235959"}, True),
        ("06_5min_1117-100000_to_1117-120000", "해외 5분봉, 20261117 10:00~12:00 → 다른 날짜·시각 봉이 옴", "overseas_chart-minute", {**ZN_5M, "inq_strt_dt": "20261117", "strt_tm": "100000", "inq_ed_dt": "20261117", "ed_tm": "120000"}, False),
        ("07_compare_domestic-5min_1117-only", "비교: 국내 5분봉, 20261117 하루 → 하루치만 옴", "domestic_chart-minute", {**KTB, "dcnt": "5", "req_qty": "300", "inq_strt_dt": "20261117", "inq_ed_dt": "20261117"}, False),
    ],
    "NH-017": [
        ("01_5min_1117_nxt-default", "국내 5분봉, 20261117 하루, nxt_key 99999999", "domestic_chart-minute", {**KTB_5M_1117, "nxt_key": "99999999"}, False),
        ("02_5min_1117_nxt-received", "국내 5분봉, 같은 요청, 받은 nxt_key 20261117084500 → 같은 페이지", "domestic_chart-minute", {**KTB_5M_1117, "nxt_key": "20261117084500"}, False),
        ("03_5min_1117_nxt-arbitrary", "국내 5분봉, 같은 요청, 임의 nxt_key 20261117120000 → 같은 페이지", "domestic_chart-minute", {**KTB_5M_1117, "nxt_key": "20261117120000"}, False),
        ("04_daily_1102-1113_nxt-default", "국내 일봉, 20261102~20261113, nxt_key 99999999", "domestic_chart-daily", {**KTB_D_1102, "nxt_key": "99999999"}, False),
        ("05_daily_1102-1113_nxt-received", "국내 일봉, 같은 요청, 받은 nxt_key 20261102 → 같은 페이지", "domestic_chart-daily", {**KTB_D_1102, "nxt_key": "20261102"}, False),
        ("06_compare_5min_no-range_p1", "비교: 국내 5분봉, 기간 없음, req_qty 10", "domestic_chart-minute", {**KTB, "dcnt": "5", "req_qty": "10", "nxt_key": "99999999"}, False),
        ("07_compare_5min_no-range_p2", "비교: 국내 5분봉, 기간 없음, req_qty 10, nxt_key 20261118145000 → 다음 페이지", "domestic_chart-minute", {**KTB, "dcnt": "5", "req_qty": "10", "nxt_key": "20261118145000"}, False),
        ("08_compare_daily_no-range_p1", "비교: 국내 일봉, 기간 없음", "domestic_chart-daily", {**KTB, "cidx_yn": "0", "req_qty": "999", "nxt_key": "99999999"}, False),
        ("09_compare_daily_no-range_p2", "비교: 국내 일봉, 기간 없음, nxt_key 20260617 → 0봉, nxt_key 0", "domestic_chart-daily", {**KTB, "cidx_yn": "0", "req_qty": "999", "nxt_key": "20260617"}, False),
        ("10_req-qty_daily_1102-1118_q5", "참고: 국내 일봉, 20261102~20261118, req_qty 5 → 기간 전체", "domestic_chart-daily", {**KTB, "cidx_yn": "0", "req_qty": "5", "inq_strt_dt": "20261102", "inq_ed_dt": "20261118", "nxt_key": "99999999"}, False),
        ("11_req-qty_5min_1117-1118_q10", "참고: 국내 5분봉, 20261117~20261118, req_qty 10 → 기간 전체", "domestic_chart-minute", {**KTB, "dcnt": "5", "cidx_yn": "0", "req_qty": "10", "inq_strt_dt": "20261117", "strt_tm": "000000", "inq_ed_dt": "20261118", "ed_tm": "235959", "nxt_key": "99999999"}, False),
        ("12_5min_0901-1118_nxt-default", "넓은 기간: 국내 5분봉, 20260901~20261118 → 2000봉에서 잘림", "domestic_chart-minute", {**KTB_5M_WIDE, "nxt_key": "99999999"}, False),
        ("13_5min_0901-1118_nxt-received", "넓은 기간: 같은 요청, 받은 nxt_key 20261015150000 → 같은 2000봉, 나머지 못 받음", "domestic_chart-minute", {**KTB_5M_WIDE, "nxt_key": "20261015150000"}, False),
    ],
}


def stamp(r: dict[str, Any]) -> str:
    return r.get("occurs1_ref_dt", "") + (" " + r["occurs1_exch_tm"] if r.get("occurs1_exch_tm") else "")


def exchange_json(ex: Exchange, at: str) -> dict[str, Any]:
    return {
        "requested_at": at,
        "request": {"method": ex.method, "url": ex.url, "headers": ex.request_headers, "body": json.loads(ex.request_body)},
        "response": {
            "status": ex.status,
            "headers": ex.response_headers,
            "duration_ms": ex.duration_ms,
            "body": mask(ex.body) if ex.body is not None else ex.response_text,
        },
    }


def summarize(body: Any) -> dict[str, Any]:
    rows = body.get("Occurs1", []) if isinstance(body, dict) else []
    return {
        "nrec": body.get("nrec") if isinstance(body, dict) else None,
        "rows": len(rows),
        "first": stamp(rows[0]) if rows else None,
        "last": stamp(rows[-1]) if rows else None,
        "nxt_key": body.get("nxt_key") if isinstance(body, dict) else None,
        "errorCode": body.get("errorCode") if isinstance(body, dict) else None,
    }


def main(ids: list[str]) -> None:
    s = get_settings()
    apis = {a.id: a for a in load_catalog(s.nh_docs_dir)}
    client = NHClient(s)
    root = s.issues_dir / "evidence"
    for issue_id in ids:
        out = root / issue_id
        out.mkdir(parents=True, exist_ok=True)
        lines = [
            f"# {issue_id} 재현 기록",
            "",
            f"- 환경: {s.base_url}",
            f"- 수집: {datetime.now(KST):%Y-%m-%d %H:%M} KST, `backend/scripts/collect_evidence.py`",
            "- 토큰은 가려서 저장했다. 날짜·시각은 응답 원문 그대로다.",
            "",
            "| 파일 | 요청 | HTTP | 페이지 | 봉 수 | 첫 봉 (최신) | 마지막 봉 | 마지막 nxt_key |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for name, desc, api_id, body, all_pages in PLANS[issue_id]:
            api = apis[api_id]
            pages: list[dict[str, Any]] = []
            req = dict(body)
            first: dict[str, Any] | None = None
            status = None
            for _ in range(80):
                at = datetime.now(KST).isoformat(timespec="seconds")
                ex = client.send(api, req)[-1]
                status = ex.status
                if first is None:
                    first = exchange_json(ex, at)
                info = summarize(ex.body)
                pages.append({"request_nxt_key": req.get("nxt_key"), **info})
                key = info["nxt_key"]
                if not all_pages or not key or set(str(key)) == {"9"} or not info["rows"]:
                    break
                req = {**req, "nxt_key": key}
            (out / f"{name}.json").write_text(json.dumps(first, ensure_ascii=False, indent=2), "utf-8")
            total = sum(p["rows"] for p in pages)
            if all_pages:
                (out / f"{name}.pages.json").write_text(
                    json.dumps({"description": desc, "pages": len(pages), "rows": total, "per_page": pages}, ensure_ascii=False, indent=2),
                    "utf-8",
                )
            files = f"[{name}.json]({name}.json)" + (f" · [페이지 요약]({name}.pages.json)" if all_pages else "")
            lines.append(
                f"| {files} | {desc} | {status} | {len(pages)} | {total:,} | {pages[0]['first']} | {pages[-1]['last']} | `{pages[-1]['nxt_key']}` |"
            )
            print(issue_id, name, status, len(pages), total, pages[0]["first"], pages[-1]["last"])
        lines += ["", "`*.json` 은 첫 요청의 요청·응답 원문이고, `*.pages.json` 은 끝까지 넘긴 모든 페이지의 요약이다.", ""]
        (out / "README.md").write_text("\n".join(lines), "utf-8")


if __name__ == "__main__":
    main(sys.argv[1:] or list(PLANS))
