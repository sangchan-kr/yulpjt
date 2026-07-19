"""출력 안전 초크포인트 (v1.12 §19, HMI handoff §17).

모든 액추에이터 출력(밸브 Down/Up, 진공, 파기)은 실제로 쓰이기 직전
이 함수를 반드시 통과한다. 표시등(타워)은 SOL_ENABLE 과 무관하므로 건드리지 않는다.

규칙:
  1. SOL_ENABLE_OK 가 OFF 면 모든 액추에이터 출력을 OFF.
  2. ADAM-4055-C #2 통신 불가면 진공/파기 출력을 OFF.
  3. 밸브 Down/Up 동시 ON → 둘 다 OFF + VALVE_INTERLOCK (블로킹).
  4. 진공/파기 동시 ON → 둘 다 OFF + VACUUM_BLOWOFF_INTERLOCK (진공 경고, 논블로킹).

반환: (blocking_alarms, vacuum_warnings) — 상위(컨트롤러)가 각각 다른 곳에 기록한다.
진공 관련은 절대 블로킹 목록에 넣지 않는다(완전 분리).
"""

from .states import Alarm, Outputs


def apply_output_safety(out: Outputs, sol_enable_ok: bool, adam2_connected: bool = True):
    blocking: list[Alarm] = []
    warnings: list[Alarm] = []

    if not sol_enable_ok:
        out.actuators_off()

    if not adam2_connected:
        # 진공/파기 는 ADAM #2 에 물려 있으므로 통신 불가 시 강제 OFF.
        out.vacuum_on = False
        out.blow_off_on = False

    if out.valve_down and out.valve_up:
        out.valve_down = False
        out.valve_up = False
        blocking.append(Alarm.VALVE_INTERLOCK)

    if out.vacuum_on and out.blow_off_on:
        out.vacuum_on = False
        out.blow_off_on = False
        warnings.append(Alarm.VACUUM_BLOWOFF_INTERLOCK)

    return blocking, warnings
