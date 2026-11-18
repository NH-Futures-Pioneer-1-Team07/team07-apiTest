"""장 운영 시간 판단 (한국 시간 기준). 공휴일은 아직 반영하지 않는다.

- 국내 주간장: 평일 08:45~15:45
- 국내 야간장: 평일 18:00~다음날 06:00
- CME: 토 07:00~월 08:00, 매일 07:00~08:00 휴장 (NH-009 답변)
- 모의 해외 주문: 07:00~24:00 이면서 거래소 장이 열려 있어야 함 (NH-009 답변)
"""

from datetime import datetime, time, timedelta, timezone
from typing import Literal

KST = timezone(timedelta(hours=9))
MarketState = Literal["주간", "야간", "장외"]


def now_kst() -> datetime:
    return datetime.now(KST)


def domestic_state(now: datetime) -> MarketState:
    t, wd = now.timetz().replace(tzinfo=None), now.weekday()  # 월=0
    if wd < 5 and time(8, 45) <= t < time(15, 45):
        return "주간"
    # 야간장은 월~금 18:00 시작, 다음날 06:00 종료
    if (wd < 5 and t >= time(18, 0)) or (1 <= wd <= 5 and t < time(6, 0)):
        return "야간"
    return "장외"


def cme_open(now: datetime) -> bool:
    t, wd = now.timetz().replace(tzinfo=None), now.weekday()
    if time(7, 0) <= t < time(8, 0):
        return False
    if wd == 5 and t >= time(7, 0):
        return False
    if wd == 6:
        return False
    if wd == 0 and t < time(8, 0):
        return False
    return True


def mock_overseas_order_open(now: datetime) -> bool:
    return now.timetz().replace(tzinfo=None) >= time(7, 0) and cme_open(now)


def condition_met(condition: str, now: datetime) -> bool:
    if condition == "국내 주간장":
        return domestic_state(now) == "주간"
    if condition == "국내 야간장":
        return domestic_state(now) == "야간"
    if condition == "국내 장외":
        return domestic_state(now) == "장외"
    if condition == "CME 열림":
        return cme_open(now)
    if condition == "모의 해외 주문 가능":
        return mock_overseas_order_open(now)
    raise ValueError(f"알 수 없는 실행 조건: {condition}")
