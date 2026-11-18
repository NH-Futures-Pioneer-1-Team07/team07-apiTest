# 테스트 케이스 작성법

케이스 하나는 YAML 파일 하나다. 파일 이름은 `TC-번호_짧은-설명.yaml`.
작성한 뒤 `backend` 폴더에서 검사하고 실행한다.

```bash
uv run python -m app.cli validate
```

```bash
uv run python -m app.cli run TC-017
```

## 기본 형식

```yaml
id: TC-017                 # 고유 ID
name: 국내 호가 정상 조회   # 화면에 보이는 이름
description: 무엇을, 왜 확인하는지
tags: [시세, 정상]
issue: NH-004              # (선택) 재확인하는 제보. 화면에 "NH-004 재확인"이 붙는다
issue_result: fail         # (선택) 제보한 문제가 그대로일 때의 결과. 기본 fail
when: [국내 주간장]         # (선택) 모두 맞을 때만 실행. 아니면 건너뜀
steps:                     # 순서대로 실행. 앞 단계가 실패하면 나머지는 건너뜀
  - name: 호가 조회
    api: domestic_price-bid  # API 문서명 (docs/nh-api 엑셀의 시트 이름)
    body: {sym: A676C000}
    expect:
      - status: 200
cleanup:                   # (선택) 결과와 관계없이 마지막에 실행
  - name: (정리) 주문 취소
    api: domestic_cancel
    if_failed: true          # 앞 단계가 실패·오류였을 때만
    body: {...}
```

실행 조건(`when`): `국내 주간장`, `국내 야간장`, `국내 장외`, `CME 열림`, `모의 해외 주문 가능`

## 단계(step)에 쓸 수 있는 것

| 키 | 설명 |
| --- | --- |
| `body` | 요청 본문. 선택 항목은 빈 문자열 대신 키를 뺀다 (NH-013) |
| `each` | 값 목록. 값마다 body에 덮어써서 한 번씩 부른다. 예: `[{req_qty: "1000"}, {req_qty: "3000"}]` |
| `extract` | 응답에서 변수를 꺼낸다. `{ord_no: ord_no}` 또는 `{p: {path: last_pric, expr: "floor(value * 0.98 * 100) / 100", format: "{:.2f}"}}` |
| `select` | 배열에서 행 하나를 고른다. `{path: Occurs1, where: {occurs1_ord_no: "${ord_no}"}}`. 고른 행은 `row.필드` |
| `wait_until` | 조건이 맞을 때까지 반복 조회. `{path: row.occurs1_ord_sts, in: ["1", "3"], interval_s: 1, timeout_s: 60}` |
| `paginate` | 다음 키를 따라 끝까지 받는다. `{next_key: nxt_key, rows: Occurs1, max_pages: 50, expect_all: [...]}`. 9로만 된 키에서 멈추고(NH-005) 같은 페이지 반복을 실패로 본다 |
| `timeout_s` | 제한 시간. 기본 30초. 넘으면 실패(성능) |
| `auth` | `false`면 토큰 없이 보낸다 |
| `market` | 토큰 발급(`api: token`) 단계에서 `overseas`면 해외 키로 발급 |

변수는 `${이름}`으로 쓴다. 기본 변수: `${today}`(YYYYMMDD), `${days_ago:60}`.

## 판정 규칙(expect)

한 줄에 하나씩 쓴다. `name:`을 붙이면 화면에 그 이름으로 보인다.

| 규칙 | 예 |
| --- | --- |
| HTTP 상태 | `status: 200`, `status: 4xx`, `status: [400, 404]` |
| 본문이 JSON | `json: true` (200인데 빈 본문을 잡는다, NH-012) |
| 오류 코드 | `error_code: ETR018`, `error_code: none` |
| 응답 시간 | `duration_ms: {lte: 3000}` |
| 필드 값 | `field: {path: last_pric, gt: 0}` — `eq`, `ne`, `in`, `regex`, `not_empty`, `exists`, `type`(string·number…), `gt`, `gte`, `lt`, `lte`, `note` |
| 배열 건수 | `count: {path: Occurs1, eq: "min(${req_qty}, 2000)"}` |
| 모든 행 규칙 | `rows: {path: Occurs1, rule: "occurs1_low_pric <= occurs1_open_pric <= occurs1_high_pric", when: "occurs1_opint_qty > 0"}` |
| 빈 행 아님 | `rows_not_blank: {path: Occurs1, fields: [occurs1_sym, occurs1_last_pric]}` (NH-004) |

식에는 숫자 계산, 비교(연속 비교 가능), `and`/`or`, `min`, `max`, `abs`, `round`, `floor`, `ceil`, `len`만 쓸 수 있다.
숫자처럼 생긴 문자열은 숫자로 바꿔서 비교한다.

## 작성 규칙

- 먼저 `issues/nh-futures/`의 제보를 확인한다. 이미 제보된 현상은 새로 탐색하지 않고, 재확인 케이스 1개만 둔다 (`issue:`).
- 재확인 케이스의 기대값은 "고쳐졌을 때의 동작"으로 쓰고 `issue_result`에 지금 결과를 적는다. 결과가 바뀌면 화면에 "NH 설명과 달라짐"이 뜬다.
- 주문 케이스는 체결되지 않을 지정가(현재가에서 멀리)와 1계약으로 하고, `cleanup`에서 남은 주문을 취소한다.
- 해외 API 거래소 코드는 종목 마스터의 ExchName 값을 쓴다 (NH-004).
- 실전 환경(`NH_ENV=real`)에서는 주문·정정·취소가 들어간 케이스를 실행하지 않는다.
