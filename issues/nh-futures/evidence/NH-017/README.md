# NH-017 재현 기록

- 환경: https://apidemo.futures.co.kr
- 수집: 2026-11-19 06:24 KST, `backend/scripts/collect_evidence.py`
- 토큰은 가려서 저장했다. 날짜·시각은 응답 원문 그대로다.

| 파일 | 요청 | HTTP | 페이지 | 봉 수 | 첫 봉 (최신) | 마지막 봉 | 마지막 nxt_key |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [01_5min_1117_nxt-default.json](01_5min_1117_nxt-default.json) | 국내 5분봉, 20261117 하루, nxt_key 99999999 | 200 | 1 | 83 | 20261117 154500 | 20261117 084500 | `20261117084500` |
| [02_5min_1117_nxt-received.json](02_5min_1117_nxt-received.json) | 국내 5분봉, 같은 요청, 받은 nxt_key 20261117084500 → 같은 페이지 | 200 | 1 | 83 | 20261117 154500 | 20261117 084500 | `20261117084500` |
| [03_5min_1117_nxt-arbitrary.json](03_5min_1117_nxt-arbitrary.json) | 국내 5분봉, 같은 요청, 임의 nxt_key 20261117120000 → 같은 페이지 | 200 | 1 | 83 | 20261117 154500 | 20261117 084500 | `20261117084500` |
| [04_daily_1102-1113_nxt-default.json](04_daily_1102-1113_nxt-default.json) | 국내 일봉, 20261102~20261113, nxt_key 99999999 | 200 | 1 | 9 | 20261112 | 20261102 | `20261102` |
| [05_daily_1102-1113_nxt-received.json](05_daily_1102-1113_nxt-received.json) | 국내 일봉, 같은 요청, 받은 nxt_key 20261102 → 같은 페이지 | 200 | 1 | 9 | 20261112 | 20261102 | `20261102` |
| [06_compare_5min_no-range_p1.json](06_compare_5min_no-range_p1.json) | 비교: 국내 5분봉, 기간 없음, req_qty 10 | 200 | 1 | 10 | 20261118 154500 | 20261118 145000 | `20261118145000` |
| [07_compare_5min_no-range_p2.json](07_compare_5min_no-range_p2.json) | 비교: 국내 5분봉, 기간 없음, req_qty 10, nxt_key 20261118145000 → 다음 페이지 | 200 | 1 | 10 | 20261118 144500 | 20261118 140000 | `20261118140000` |
| [08_compare_daily_no-range_p1.json](08_compare_daily_no-range_p1.json) | 비교: 국내 일봉, 기간 없음 | 200 | 1 | 105 | 20261118 | 20260617 | `20260617` |
| [09_compare_daily_no-range_p2.json](09_compare_daily_no-range_p2.json) | 비교: 국내 일봉, 기간 없음, nxt_key 20260617 → 0봉, nxt_key 0 | 200 | 1 | 0 | None | None | `0` |
| [10_req-qty_daily_1102-1118_q5.json](10_req-qty_daily_1102-1118_q5.json) | 참고: 국내 일봉, 20261102~20261118, req_qty 5 → 기간 전체 | 200 | 1 | 12 | 20261117 | 20261102 | `20261102` |
| [11_req-qty_5min_1117-1118_q10.json](11_req-qty_5min_1117-1118_q10.json) | 참고: 국내 5분봉, 20261117~20261118, req_qty 10 → 기간 전체 | 200 | 1 | 166 | 20261118 154500 | 20261117 084500 | `20261117084500` |

`*.json` 은 첫 요청의 요청·응답 원문이고, `*.pages.json` 은 끝까지 넘긴 모든 페이지의 요약이다.
