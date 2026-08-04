"""제어 상태머신의 상태/알람 정의 (v1.12 §11·12·14).

진공 흡착은 자동 시퀀스에서 제외(수동 HMI 토글, 결정3)되어 Auto 시퀀스는
가압만 담당한다.
"""

from dataclasses import dataclass
from enum import Enum


class State(Enum):
    BOOT = "BOOT"
    AUTO_IDLE = "AUTO_IDLE"
    AUTO_PRECHECK = "AUTO_PRECHECK"
    AUTO_MOVE_DOWN = "AUTO_MOVE_DOWN"
    AUTO_DWELL_DOWN = "AUTO_DWELL_DOWN"
    AUTO_MOVE_UP = "AUTO_MOVE_UP"
    AUTO_DWELL_UP = "AUTO_DWELL_UP"
    AUTO_COUNT_UPDATE = "AUTO_COUNT_UPDATE"
    AUTO_COMPLETE = "AUTO_COMPLETE"
    MANUAL_IDLE = "MANUAL_IDLE"
    MANUAL_MOVE_UP = "MANUAL_MOVE_UP"    # 교체 위치: 상승 센서 닿을 때까지 이동
    SAFETY_STOP = "SAFETY_STOP"
    ERROR = "ERROR"


class Alarm(Enum):
    # --- 블로킹 알람: 기계 상태(ERROR)·자동운전 정지에 영향 ---
    VALVE_INTERLOCK = "VALVE_INTERLOCK"                  # Down/Up 동시 명령
    MANUAL_CONFLICT = "MANUAL_CONFLICT"                  # Manual Up/Down 동시 입력
    DOWN_TIMEOUT = "DOWN_TIMEOUT"                        # Down 위치 미도달
    UP_TIMEOUT = "UP_TIMEOUT"                            # Up 위치 미도달
    LOAD_OVER_LIMIT = "LOAD_OVER_LIMIT"                  # 하중 상한 초과
    ADAM_COMM_ERROR = "ADAM_COMM_ERROR"                  # Modbus 통신 오류

    # --- 진공 경고: 논블로킹. 자동운전/기계 상태/타워에 영향 없음 (완전 분리) ---
    VACUUM_NOT_REACHED = "VACUUM_NOT_REACHED"            # Vacuum ON 후 timeout 내 미도달
    VACUUM_SIGNAL_ABNORMAL = "VACUUM_SIGNAL_ABNORMAL"    # Vacuum OFF 인데 OK 장시간 ON
    VACUUM_BLOWOFF_INTERLOCK = "VACUUM_BLOWOFF_INTERLOCK"  # 진공/파기 동시 ON


# SAFETY_STOP 은 상태이면서, HMI Safety Reset 로만 해제된다.
# 블로킹 알람 = 기계 상태를 ERROR 로 만들고 자동운전을 막는다.
BLOCKING_ALARMS = frozenset({
    Alarm.VALVE_INTERLOCK, Alarm.MANUAL_CONFLICT, Alarm.DOWN_TIMEOUT,
    Alarm.UP_TIMEOUT, Alarm.LOAD_OVER_LIMIT, Alarm.ADAM_COMM_ERROR,
})
# 진공 경고 = 논블로킹. 표시만 하고 어떤 자동 동작에도 영향 주지 않는다.
VACUUM_WARNINGS = frozenset({
    Alarm.VACUUM_NOT_REACHED, Alarm.VACUUM_SIGNAL_ABNORMAL, Alarm.VACUUM_BLOWOFF_INTERLOCK,
})


@dataclass
class Outputs:
    """한 스캔에서 계산된 '원하는' 출력. safety 초크포인트를 거쳐 실제로 쓰인다.

    IO map v0.2: 타워램프 제거 → 버튼 내장 램프 4개 + 부저.
    램프/부저는 액추에이터가 아니라 표시용이라 safety 초크포인트가 끄지 않는다.
    """
    valve_down: bool = False
    valve_up: bool = False
    vacuum_on: bool = False
    blow_off_on: bool = False
    lamp_auto_start: bool = False
    lamp_auto_stop: bool = False       # 대표 알람 램프
    lamp_manual_up: bool = False
    lamp_manual_down: bool = False
    buzzer: bool = False

    def actuators_off(self) -> None:
        self.valve_down = self.valve_up = self.vacuum_on = self.blow_off_on = False
