from datetime import datetime

import httpx

from app.market import KST
from tests.conftest import case, ok

PRICE = "/trade/v1/domestic/price"
MINUTE = "/trade/v1/domestic/chart-minute"
ORDER = "/trade/v1/domestic/order"
HISTORY = "/trade/v1/domestic/order-history"
O_MINUTE = "/trade/v1/overseas/chart-minute"


def test_success_and_token_reuse(make_runner, fake):
    fake.on(PRICE, ok({"sym_nm": "10년국채", "last_pric": "108.71"}))
    c = case({"steps": [{"name": "a", "api": "domestic_price", "body": {"sym": "X"}, "expect": [{"status": 200}, {"field": {"path": "last_pric", "gt": 100}}]}] * 2})
    run = make_runner().run(c)
    assert run["status"] == "success"
    assert fake.tokens_issued == 1
    step = run["steps"][0]
    assert step["request"]["headers"]["Authorization"].startswith("Bearer tok1"[:11])
    assert "tok1" not in step["request"]["headers"]["Authorization"][7:] or step["request"]["headers"]["Authorization"].endswith("••••••")


def test_each_and_count_expression(make_runner, fake):
    fake.on(MINUTE, lambda req, body: httpx.Response(200, json={"Occurs1": [{}] * min(int(body["req_qty"]), 2000)}))
    c = case({"steps": [{"name": "m", "api": "domestic_chart-minute", "body": {"nght_tp": "1", "sym": "X"}, "each": [{"req_qty": "1000"}, {"req_qty": "3000"}], "expect": [{"count": {"path": "Occurs1", "eq": "${req_qty}"}}]}]})
    run = make_runner().run(c)
    assert run["status"] == "fail"
    assert [s["status"] for s in run["steps"]] == ["success", "fail"]
    assert run["failure"]["actual"] == "2000건"
    assert run["match"] == {"kind": "new"}


def test_slow_backend_retried_once_for_queries(make_runner, fake):
    fake.on(MINUTE, [lambda r, b: httpx.Response(504, json={"errorCode": "EGW032"}), ok({"Occurs1": []})])
    c = case({"steps": [{"name": "m", "api": "domestic_chart-minute", "body": {"nght_tp": "1", "sym": "X"}, "expect": [{"status": 200}]}]})
    run = make_runner().run(c)
    assert run["status"] == "success"
    assert fake.count(MINUTE) == 2
    assert run["steps"][0]["superseded"] is True
    assert "EGW032" in run["steps"][0]["note"]


def test_orders_are_never_resent(make_runner, fake):
    fake.on(ORDER, lambda r, b: httpx.Response(504, json={"errorCode": "EGW032"}))
    c = case({"steps": [{"name": "o", "api": "domestic_order", "body": {"sym": "X", "trd_div": "1", "ord_tp_cd": "1", "ord_qty": "1", "exec_cnd_cd": "1"}, "expect": [{"status": 200}]}]})
    run = make_runner().run(c)
    assert run["status"] == "fail"
    assert fake.count(ORDER) == 1


def test_token_reissued_on_rejection(make_runner, fake):
    fake.on(PRICE, [lambda r, b: httpx.Response(401, json={"errorCode": "EGW052"}), ok({"last_pric": "1"})])
    c = case({"steps": [{"name": "a", "api": "domestic_price", "body": {"sym": "X"}, "expect": [{"status": 200}]}]})
    assert make_runner().run(c)["status"] == "success"
    assert fake.tokens_issued == 2


def test_empty_body_is_not_json(make_runner, fake):
    fake.on("/trade/v1/overseas/price", lambda r, b: httpx.Response(200, content=b""))
    c = case({"issue": "NH-012", "steps": [{"name": "p", "api": "overseas_price", "body": {"Iccurs1": []}, "expect": [{"json": True}]}]})
    run = make_runner().run(c)
    assert run["status"] == "fail"
    assert run["steps"][0]["assertions"][0]["actual"] == "빈 문자열"
    assert run["match"] == {"kind": "known", "issueId": "NH-012"}


def test_regression_case_reports_behavior_change(make_runner, fake):
    fake.on(PRICE, ok({"last_pric": "1"}))
    c = case({"issue": "NH-004", "issue_result": "fail", "steps": [{"name": "a", "api": "domestic_price", "body": {"sym": "X"}, "expect": [{"status": 200}]}]})
    run = make_runner().run(c)
    assert run["status"] == "success"
    assert run["match"] == {"kind": "changed", "issueId": "NH-004"}


def test_pagination_stops_on_nines(make_runner, fake):
    pages = [
        ok({"nxt_key": "2026", "Occurs1": [{"d": 1}, {"d": 2}]}),
        ok({"nxt_key": "9" * 32, "Occurs1": [{"d": 3}]}),
        ok({"nxt_key": "x", "Occurs1": [{"d": 1}, {"d": 2}]}),
    ]
    fake.on(O_MINUTE, pages)
    c = case({"steps": [{"name": "p", "api": "overseas_chart-minute", "body": {"exch_cd": "FCME", "sym": "Z", "nxt_key": "99999999"}, "paginate": {"expect_all": [{"count": {"path": "rows", "eq": 3}}]}, "expect": [{"status": 200}]}]})
    run = make_runner().run(c)
    assert run["status"] == "success", run
    assert fake.count(O_MINUTE) == 2
    assert fake.calls[-1][1]["nxt_key"] == "2026"
    assert "NH-005" in run["steps"][-1]["note"]


def test_pagination_detects_repeated_page(make_runner, fake):
    fake.on(O_MINUTE, ok({"nxt_key": "123", "Occurs1": [{"d": 1}]}))
    c = case({"steps": [{"name": "p", "api": "overseas_chart-minute", "body": {"exch_cd": "FCME", "sym": "Z"}, "paginate": {}, "expect": [{"status": 200}]}]})
    run = make_runner().run(c)
    assert run["status"] == "fail"
    assert "같음" in run["steps"][-1]["assertions"][0]["actual"]


def test_wait_until_selects_row_and_extract_math(make_runner, fake):
    fake.on(PRICE, ok({"last_pric": "100.00"}))
    fake.on(ORDER, ok({"ord_no": "0000000077", "msg_cd": "", "msg_cntn": ""}))
    fake.on(HISTORY, [
        ok({"Occurs1": [{"occurs1_ord_no": "77", "occurs1_ord_sts": ""}]}),
        ok({"Occurs1": [{"occurs1_ord_no": "77", "occurs1_ord_sts": "1"}]}),
    ])
    c = case({
        "steps": [
            {"name": "가격", "api": "domestic_price", "body": {"sym": "X"}, "extract": {"p": {"path": "last_pric", "expr": "floor(value * 0.98 * 100) / 100", "format": "{:.2f}"}}},
            {"name": "주문", "api": "domestic_order", "body": {"sym": "X", "trd_div": "1", "ord_tp_cd": "1", "ord_qty": "1", "ord_pric": "${p}", "exec_cnd_cd": "1"}, "extract": {"ord_no": "ord_no"}},
            {"name": "내역", "api": "domestic_order-history", "body": {"trd_div": "0", "exec_div": "0", "trd_tm_div_cd": "0", "ord_div_cd": "0"},
             "select": {"path": "Occurs1", "where": {"occurs1_ord_no": "${ord_no}"}},
             "wait_until": {"path": "row.occurs1_ord_sts", "in": ["1"], "interval_s": 0, "timeout_s": 5},
             "expect": [{"field": {"path": "row.occurs1_ord_sts", "eq": "1"}}]},
        ]
    })
    run = make_runner().run(c)
    assert run["status"] == "success", run
    order_call = next(b for p, b, _ in fake.calls if p == ORDER)
    assert order_call["ord_pric"] == "98.00"
    assert "2번 조회" in run["steps"][2]["note"]


def test_failed_step_skips_rest_and_runs_cleanup(make_runner, fake):
    fake.on(PRICE, lambda r, b: httpx.Response(500, json={"errorCode": "X"}))
    fake.on("/trade/v1/domestic/cancel", ok({}))
    c = case({
        "steps": [{"name": "a", "api": "domestic_price", "body": {"sym": "X"}, "expect": [{"status": 200}]}, {"name": "b", "api": "domestic_price", "body": {"sym": "X"}}],
        "cleanup": [{"name": "정리", "api": "domestic_cancel", "if_failed": True, "body": {"sym": "X", "trd_div": "1", "ord_qty": "1", "org_ord_no": "1"}}],
    })
    run = make_runner().run(c)
    assert [s["status"] for s in run["steps"]] == ["fail", "skipped", "success"]
    assert fake.count("/trade/v1/domestic/cancel") == 1


def test_skipped_outside_market_hours(make_runner, fake):
    sunday = datetime(2026, 11, 22, 10, 0, tzinfo=KST)
    c = case({"when": ["국내 주간장"], "steps": [{"name": "a", "api": "domestic_price", "body": {"sym": "X"}}]})
    run = make_runner(clock=sunday).run(c)
    assert run["status"] == "skipped" and run["skipKind"] == "시간대 조건 밖"
    assert fake.calls == []


def test_real_env_blocks_orders(make_runner, fake):
    c = case({"steps": [{"name": "o", "api": "domestic_order", "body": {"sym": "X", "trd_div": "1", "ord_tp_cd": "1", "ord_qty": "1", "exec_cnd_cd": "1"}}]})
    run = make_runner(nh_env="real").run(c)
    assert run["status"] == "skipped" and run["skipKind"] == "실전 차단"
    assert fake.calls == []


def test_missing_keys_is_error(make_runner, fake):
    c = case({"steps": [{"name": "a", "api": "overseas_price", "body": {"Iccurs1": []}}]})
    run = make_runner(nh_overseas_app_key=None).run(c)
    assert run["status"] == "error" and run["errorKind"] == "인증 설정 누락"


def test_connection_failure_is_error(make_runner, fake):
    def boom(req, body):
        raise httpx.ConnectError("down")

    fake.on(PRICE, boom)
    c = case({"steps": [{"name": "a", "api": "domestic_price", "body": {"sym": "X"}}]})
    run = make_runner().run(c)
    assert run["status"] == "error" and run["errorKind"] == "연결 실패"


def test_timeout_is_failure_not_error(make_runner, fake):
    def slow(req, body):
        raise httpx.ReadTimeout("slow")

    fake.on(PRICE, slow)
    c = case({"steps": [{"name": "a", "api": "domestic_price", "body": {"sym": "X"}, "timeout_s": 1}]})
    run = make_runner().run(c)
    assert run["status"] == "fail"
    assert run["steps"][0]["assertions"][0]["rule"] == "응답 시간"


def test_invalid_case_is_error(make_runner):
    c = case({"steps": [{"name": "a", "api": "domestic_price", "body": {"nope": "1", "sym": "${undefined}"}}]})
    run = make_runner().run(c)
    assert run["status"] == "error" and run["errorKind"] == "케이스 파일 오류"
    assert "nope" in run["errorReason"] and "undefined" in run["errorReason"]


def test_rows_rule_and_blank_rows(make_runner, fake):
    fake.on("/trade/v1/overseas/price", ok({"Occurs1": [{"occurs1_sym": "", "occurs1_last_pric": ""}]}))
    c = case({"steps": [{"name": "p", "api": "overseas_price", "body": {"Iccurs1": []}, "expect": [
        {"rows_not_blank": {"path": "Occurs1"}},
        {"rows": {"path": "Occurs1", "rule": "occurs1_last_pric != ''"}},
    ]}]})
    run = make_runner().run(c)
    a = run["steps"][0]["assertions"]
    assert [x["passed"] for x in a] == [False, False]


def test_rows_rule_passes_when_nh_returns_zero_rows(make_runner, fake):
    # NH는 0건이면 Occurs1 키를 빼고 nrec 를 "0000" 으로 준다
    fake.on("/trade/v1/domestic/open-interest", ok({"nxt_key": "", "nrec": "0000"}))
    c = case({"steps": [{"name": "잔고", "api": "domestic_open-interest", "body": {}, "expect": [{"rows": {"path": "Occurs1", "rule": "occurs1_avg_pric > 0"}}]}]})
    run = make_runner().run(c)
    assert run["status"] == "success"
    assert run["steps"][0]["assertions"][0]["actual"] == "조회 결과 0건 (nrec 0)"
