# NH-014 재현 기록

- 환경: https://apidemo.futures.co.kr
- 수집: 2026-11-19 04:10 KST, `backend/scripts/collect_evidence.py`
- 토큰은 가려서 저장했다. 날짜·시각은 응답 원문 그대로다.

| 파일 | 요청 | HTTP | 페이지 | 봉 수 | 첫 봉 (최신) | 마지막 봉 | 마지막 nxt_key |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [01_daily_start-1101_end-default.json](01_daily_start-1101_end-default.json) | 해외 일봉, 시작 20261101, 종료 기본값 → 시작일 무시 | 200 | 1 | 172 | 20261118 | 20260324 | `99999999999999999999999999999999` |
| [02_daily_start-1101_end-1231.json](02_daily_start-1101_end-1231.json) | 해외 일봉, 시작 20261101, 종료 20261231 → 시작일 적용 | 200 | 1 | 13 | 20261118 | 20261102 | `99999999999999999999999999999999` |
| [03_linked-daily_start-20230112_end-default_all-pages.json](03_linked-daily_start-20230112_end-default_all-pages.json) · [페이지 요약](03_linked-daily_start-20230112_end-default_all-pages.pages.json) | 해외 연결 일봉, 시작 20230112, 종료 기본값, 끝까지 | 200 | 13 | 7,026 | 20261118 | 19980928 | `99999999999999999999999999999999` |
| [04_5min_start-1117_end-default_all-pages.json](04_5min_start-1117_end-default_all-pages.json) · [페이지 요약](04_5min_start-1117_end-default_all-pages.pages.json) | 해외 5분봉, 시작 20261117 000000, 종료 기본값, 끝까지 | 200 | 43 | 20,983 | 20261119 041000 | 20260330 070000 | `99999999999999999999999999999999` |
| [05_5min_start-1117_end-1119_all-pages.json](05_5min_start-1117_end-1119_all-pages.json) · [페이지 요약](05_5min_start-1117_end-1119_all-pages.pages.json) | 해외 5분봉, 시작 20261117 000000, 종료 20261119 235959, 끝까지 | 200 | 2 | 604 | 20261119 041000 | 20261117 000000 | `99999999999999999999999999999999` |
| [06_compare_domestic-daily_start-1101_end-default.json](06_compare_domestic-daily_start-1101_end-default.json) | 비교: 국내 일봉, 시작 20261101, 종료 기본값 → 시작일 적용 | 200 | 1 | 13 | 20261118 | 20261102 | `20261102` |

`*.json` 은 첫 요청의 요청·응답 원문이고, `*.pages.json` 은 끝까지 넘긴 모든 페이지의 요약이다.
