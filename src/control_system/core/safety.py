"""출력 안전 초크포인트 (v1.12 §19).

모든 액추에이터 출력(밸브 Down/Up, 진공, 파기)은 실제로 쓰이기 직전
이 함수를 반드시 통과한다. 표시등(타워)은 SOL_ENABLE 과 무관하므로 건드리지 않는다.

규칙:
  1. SOL_ENABLE_OK 가 OFF 면 모든 액추에이터 출력을 OFF.
  2. 밸브 Down/Up 이 동시 ON 이면 둘 다 OFF + VALVE_INTERLOCK.
  3. 진공/파기가 동시 ON 이면 둘 다 OFF + VACUUM_BLOWOFF_INTERLOCK.
"""

from .states import Alarm, Outputs


def apply_output_safety(out: Outputs, sol_enable_ok: bool) -> list[Alarm]:
    """out 을 제자리에서 안전 규칙에 맞게 강제하고, 발생한 알람 목록을 돌려준다."""
    alarms: list[Alarm] = []

    if not sol_enable_ok:
        out.actuators_off()

    if out.valve_down and out.valve_up:
        out.valve_down = False
        out.valve_up = False
        alarms.append(Alarm.VALVE_INTERLOCK)

    if out.vacuum_on and out.blow_off_on:
        out.vacuum_on = False
        out.blow_off_on = False
        alarms.append(Alarm.VACUUM_BLOWOFF_INTERLOCK)

    return alarms
