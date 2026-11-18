from datetime import datetime

import pytest

from app.catalog import load_catalog
from app.config import get_settings
from app.expr import ExprError, evaluate, render
from app.market import KST, cme_open, domestic_state


def test_catalog_reads_nh_excel_spec():
    apis = load_catalog(get_settings().nh_docs_dir)
    by_id = {a.id: a for a in apis}
    assert len(apis) == 50
    assert "domestic_open-position" in by_id  # 2026-11-19 엑셀에서 새로 생긴 API
    assert "최대 999건" in next(f.description for f in by_id["domestic_chart-daily"].input if f.key == "req_qty")
    order = by_id["domestic_order"]
    assert order.url == "/trade/v1/domestic/order" and order.is_order and order.category == "주문"
    assert {f.key for f in order.input if f.required} >= {"sym", "trd_div", "ord_qty"}
    assert by_id["overseas_price"].market == "overseas"
    assert by_id["KA"].protocol == "WS"


def test_expressions():
    assert evaluate("min(3000, 2000)") == 2000
    assert evaluate("a <= b <= c", {"a": "1.5", "b": "2", "c": "3"}) is True
    assert evaluate("x > 0 and y > 0", {"x": "1", "y": "0"}) is False
    with pytest.raises(ExprError):
        evaluate("__import__('os')")
    with pytest.raises(ExprError):
        evaluate("open('x')")


def test_render_variables():
    now = datetime(2026, 11, 19, 9, 0, tzinfo=KST)
    assert render({"a": "${x}", "b": ["${today}"]}, {"x": 1}, now) == {"a": "1", "b": ["20261119"]}
    assert render("${days_ago:1}", {}, now) == "20261118"
    with pytest.raises(ExprError):
        render("${missing}", {}, now)


@pytest.mark.parametrize(
    ("when", "domestic", "cme"),
    [
        (datetime(2026, 11, 18, 10, 0), "주간", True),  # 수 오전
        (datetime(2026, 11, 18, 7, 30), "장외", False),  # CME 일일 휴장
        (datetime(2026, 11, 18, 20, 0), "야간", True),
        (datetime(2026, 11, 21, 3, 0), "야간", True),  # 토 새벽은 금요일 야간장
        (datetime(2026, 11, 22, 17, 15), "장외", False),  # 일요일 (NH-009)
    ],
)
def test_market_hours(when, domestic, cme):
    t = when.replace(tzinfo=KST)
    assert domestic_state(t) == domestic
    assert cme_open(t) == cme


def test_repo_case_files_are_valid():
    from app.cases import load_cases, validate_case

    s = get_settings()
    apis = {a.id: a for a in load_catalog(s.nh_docs_dir)}
    cases, errors = load_cases(s.cases_dir)
    assert errors == []
    assert cases
    for c in cases:
        assert validate_case(c, apis) == [], c.id


def test_older_spec_folder_still_readable():
    """기존 팀 레포의 명세 폴더(10/24 엑셀 + 마크다운)도 읽을 수 있어야 한다."""
    from pathlib import Path

    md_dir = Path(__file__).resolve().parents[3] / "pioneer-1st-code-team07" / "docs" / "nh-api"
    if not (md_dir / "apis").is_dir():
        pytest.skip("마크다운 명세 폴더가 없음")
    apis = {a.id: a for a in load_catalog(md_dir)}
    assert len(apis) == 49 and apis["domestic_order"].is_order
