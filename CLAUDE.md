# team07-apiTest

NH선물 API를 사용자 입장에서 실제로 호출해 검증하고, 실패가 이미 제보된 건인지 관리하는 서비스.
요구사항은 `docs/REQUIREMENTS.md`.

## 구조

| 경로 | 내용 |
| --- | --- |
| `backend/` | FastAPI 서버, 실행기, CLI (Python 3.12, uv) |
| `frontend/` | 화면 (Vite, React, TypeScript). `/api`는 백엔드(8000)로 넘긴다 |
| `testcases/nh-futures/` | 테스트 케이스 YAML. 작성법은 `testcases/README.md` |
| `issues/nh-futures/` | 제보 내역 YAML (NH-001.yaml …). 화면의 제보 내역이 이 파일을 읽고 쓴다 |
| `docs/` | 요구사항, 제보 정리 |

API 명세는 `docs/nh-api/전체_API_문서.xlsx`(NH 배포 엑셀, 2026-11-19 받음)에서 읽는다. 새 엑셀을 받으면 이 파일을 바꾸고 백엔드를 다시 시작한다. 엑셀이 없으면 `apis/*.md`를 읽는다 (`NH_DOCS_DIR`로 폴더를 바꿀 수 있다).

## 실행

```bash
cd backend && uv run uvicorn app.main:create_app --factory --reload --timeout-graceful-shutdown 2
```

```bash
cd frontend && npm run dev
```

```bash
cd backend && uv run pytest
```

케이스 검사·실행은 `backend`에서 `uv run python -m app.cli validate | list | run TC-001 | run --tag 시세 | run --all`.

## 테스트 케이스를 만들 때

1. `issues/nh-futures/`에서 같은 API의 제보와 사용 규칙(`rules`)을 먼저 읽는다. 이미 제보된 현상은 재확인 케이스 1개만 두고 새로 탐색하지 않는다.
2. API 명세(엑셀의 시트, 시트 이름이 문서명)의 INPUT·OUTPUT 필드 이름을 그대로 쓴다. 명세에 없는 요청 필드는 검사에서 막힌다.
3. 작성 후 `validate`로 검사하고, 사용자가 원하면 `run`으로 실행한다.

## 안전 규칙

- 주문·정정·취소는 모의 환경에서만 실행한다. 실행기도 실전에서는 막는다.
- 주문 케이스는 체결되지 않을 지정가와 1계약, `cleanup` 취소를 넣는다. 주문 API는 자동으로 다시 보내지 않는다.
- `backend/.env`의 키는 읽거나 출력하지 않는다. 기록에는 토큰·키·계좌번호를 가려서 남긴다.
