"""이름 있는 I/O 신호 맵과 IO 파사드 (v1.12 §5·6·9·18).

상태머신/HMI 는 채널 번호가 아니라 신호 이름(예: ``DO1.K_VALVE_DOWN``)만 다룬다.
어느 모듈의 몇 번 채널인지는 여기와 ``IO`` 에만 존재한다.
"""

from enum import IntEnum


class DI1(IntEnum):
    """ADAM-4055-C #1 Digital Input (프레스/스위치/피드백)."""
    MODE_AUTO = 0        # Auto/Manual 셀렉터 (Auto=ON)
    AUTO_START_PB = 1
    AUTO_STOP_PB = 2
    MANUAL_UP_PB = 3
    MANUAL_DOWN_PB = 4
    CYL_UP_POS = 5       # 실린더 상승 위치 센서
    CYL_DOWN_POS = 6     # 실린더 하강 위치 센서
    SOL_ENABLE_OK = 7    # EMO+Area 하드웨어 인터록 피드백


class DO1(IntEnum):
    """ADAM-4055-C #1 Digital Output (타워램프/프레스 밸브)."""
    TOWER_GREEN = 0
    TOWER_YELLOW = 1
    TOWER_RED = 2
    TOWER_BUZZER = 3
    K_VALVE_DOWN = 4     # DS6340 하강 솔레노이드
    K_VALVE_UP = 5       # DS6340 상승 솔레노이드
    SPARE_DO_1 = 6
    SPARE_DO_2 = 7


class DI2(IntEnum):
    """ADAM-4055-C #2 Digital Input (진공 이젝터/예비)."""
    VACUUM_OK = 0        # ZK2A 진공 스위치 (NPN — 필요 시 config 로 반전)
    VACUUM_RELEASE_OK = 1
    AIR_PRESS_OK = 2
    VACUUM_UNIT_ALARM = 3
    SPARE_DI_4 = 4
    SPARE_DI_5 = 5
    SPARE_DI_6 = 6
    SPARE_DI_7 = 7


class DO2(IntEnum):
    """ADAM-4055-C #2 Digital Output (진공/파기)."""
    K_VACUUM_ON = 0      # 흡착/진공 발생
    K_BLOW_OFF_ON = 1    # 파기 blow-off
    SPARE_DO_2 = 2
    SPARE_DO_3 = 3
    SPARE_DO_4 = 4
    SPARE_DO_5 = 5
    SPARE_DO_6 = 6
    SPARE_DO_7 = 7


class AI(IntEnum):
    """ADAM-4017+-F Analog Input."""
    LOADCELL_CURRENT = 0     # NCT-I420 4-20 mA
    SPARE_AI_1 = 1
    SPARE_AI_2 = 2
    SPARE_AI_3 = 3
    SPARE_AI_4 = 4
    SPARE_AI_5 = 5
    SPARE_AI_6 = 6
    SPARE_AI_7 = 7


class IO:
    """두 ADAM-4055-C 와 ADAM-4017+ 를 이름 있는 신호로 접근하는 파사드.

    입력은 ``refresh_inputs()`` 로 한 스캔에 한 번 읽어 캐시하고,
    출력은 ``set()`` 으로 스테이징한 뒤 ``flush_outputs()`` 에서 한꺼번에 쓴다
    (v1.12 §19 의 단일 출력 초크포인트를 지원하기 위함).
    """

    def __init__(self, adam1, adam2, adam4017, *, input_invert=frozenset()) -> None:
        self._m1 = adam1
        self._m2 = adam2
        self._ai = adam4017
        self._invert = frozenset(input_invert)   # 반전할 DI 신호 집합
        self._di1 = [False] * 8
        self._di2 = [False] * 8
        self._ma = [4.0] * 8

    # --- 입력 -------------------------------------------------------------
    def refresh_inputs(self) -> None:
        self._di1 = self._m1.read_di()
        self._di2 = self._m2.read_di()
        self._ma = self._ai.read_all_ma()

    def di(self, sig) -> bool:
        if isinstance(sig, DI1):
            v = self._di1[int(sig)]
        elif isinstance(sig, DI2):
            v = self._di2[int(sig)]
        else:
            raise TypeError(f"DI 신호가 아님: {sig!r}")
        return (not v) if sig in self._invert else v

    def ma(self, sig) -> float:
        if not isinstance(sig, AI):
            raise TypeError(f"AI 신호가 아님: {sig!r}")
        return self._ma[int(sig)]

    # --- 출력 -------------------------------------------------------------
    def set(self, sig, value: bool) -> None:
        if isinstance(sig, DO1):
            self._m1.stage_do(int(sig), value)
        elif isinstance(sig, DO2):
            self._m2.stage_do(int(sig), value)
        else:
            raise TypeError(f"DO 신호가 아님: {sig!r}")

    def get_out(self, sig) -> bool:
        if isinstance(sig, DO1):
            return self._m1.staged_do(int(sig))
        if isinstance(sig, DO2):
            return self._m2.staged_do(int(sig))
        raise TypeError(f"DO 신호가 아님: {sig!r}")

    def flush_outputs(self) -> None:
        self._m1.flush_do()
        self._m2.flush_do()

    def all_outputs_off(self) -> None:
        """스테이징 버퍼의 모든 DO 를 OFF 로 (아직 쓰지는 않음)."""
        for ch in range(8):
            self._m1.stage_do(ch, False)
            self._m2.stage_do(ch, False)
