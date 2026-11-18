"""명령줄 실행. Claude가 케이스를 만든 뒤 바로 검사·실행해 볼 때 쓴다.

uv run python -m app.cli validate
uv run python -m app.cli list
uv run python -m app.cli run TC-002 TC-003
uv run python -m app.cli run --tag 시세
uv run python -m app.cli run --all
"""

import argparse
import json
import sys

from app.config import get_settings
from app.service import Service

LABEL = {"success": "성공", "fail": "실패", "error": "오류", "skipped": "건너뜀", "running": "진행중"}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="apitest")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate", help="케이스 파일 검사")
    sub.add_parser("list", help="케이스 목록")
    r = sub.add_parser("run", help="케이스 실행")
    r.add_argument("ids", nargs="*")
    r.add_argument("--tag")
    r.add_argument("--all", action="store_true")
    r.add_argument("--json", action="store_true", help="결과를 JSON으로 출력")
    args = p.parse_args(argv)

    svc = Service(get_settings())
    cases, problems = svc.load()

    if args.cmd == "validate":
        for pr in problems:
            print(f"✕ {pr['file']}")
            for x in pr["problems"]:
                print(f"    {x}")
        print(f"케이스 {len(cases)}개, 문제 있는 파일 {len(problems)}개")
        return 1 if problems else 0

    if args.cmd == "list":
        links = svc.case_issue_map(cases)
        for c in cases:
            issue = f" [{links[c.id]} 재확인]" if c.id in links else ""
            print(f"{c.id}  {c.kind()}  {c.name}{issue}  ({', '.join(c.api_ids())})")
        return 0

    targets = [c for c in cases if args.all or c.id in args.ids or (args.tag and args.tag in c.tags)]
    if not targets:
        print("실행할 케이스가 없습니다. ID, --tag, --all 중 하나를 주세요", file=sys.stderr)
        return 2
    worst = 0
    for c in targets:
        run = svc.run_now(c.id)
        status = run["status"]
        line = f"{LABEL[status]:<4} {c.id} {c.name} ({run['durationMs']}ms)"
        if status == "fail":
            line += f"\n     {run['failure']['reason']}"
            m = run.get("match") or {}
            line += f"\n     제보: {m.get('issueId', '기존 제보 없음')} ({m.get('kind')})"
        elif status == "error":
            line += f"\n     {run.get('errorKind')}: {run.get('errorReason')}"
        elif status == "skipped":
            line += f"\n     {run.get('skipReason')}"
        print(line)
        if args.json:
            print(json.dumps(run, ensure_ascii=False, indent=2))
        worst = max(worst, {"success": 0, "skipped": 0, "fail": 1, "error": 2}.get(status, 0))
    return worst


if __name__ == "__main__":
    sys.exit(main())
