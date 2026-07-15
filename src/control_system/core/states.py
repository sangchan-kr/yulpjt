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
    SAFETY_STOP = "SAFETY_STOP"
    ERROR = "ERROR"


class Alarm(Enum):
    VALVE_INTERLOCK = "VALVE_INTERLOCK"                  # Down/Up 동시 명령
    MANUAL_CONFLICT = "MANUAL_CONFLICT"                  # Manual Up/Down 동시 입력
    DOWN_TIMEOUT = "DOWN_TIMEOUT"                        # Down 위치 미도달
    UP_TIMEOUT = "UP_TIMEOUT"                            # Up 위치 미도달
    VACUUM_FAIL = "VACUUM_FAIL"                          # 진공 timeout
    VACUUM_LOSS = "VACUUM_LOSS"                          # 유지 중 VACUUM_OK 이탈
    VACUUM_BLOWOFF_INTERLOCK = "VACUUM_BLOWOFF_INTERLOCK"  # 진공/파기 동시 ON
    ADAM_COMM_ERROR = "ADAM_COMM_ERROR"                  # Modbus 통신 오류
    LOAD_OVER_LIMIT = "LOAD_OVER_LIMIT"                  # 하중 상한 초과


# SAFETY_STOP 은 상태이면서, HMI Safety Reset 로만 해제된다.
# 아래 알람들은 원인 제거 후 Alarm Clear 로 해제 가능(clearable).
CLEARABLE_ALARMS = frozenset(Alarm)


@dataclass
class Outputs:
    """한 스캔에서 계산된 '원하는' 출력. safety 초크포인트를 거쳐 실제로 쓰인다."""
    valve_down: bool = False
    valve_up: bool = False
    vacuum_on: bool = False
    blow_off_on: bool = False
    tower_green: bool = False
    tower_yellow: bool = False
    tower_red: bool = False
    tower_buzzer: bool = False

    def actuators_off(self) -> None:
        self.valve_down = self.valve_up = self.vacuum_on = self.blow_off_on = False
