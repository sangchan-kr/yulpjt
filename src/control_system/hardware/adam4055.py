"""ADAM-4055-C — 절연 디지털 I/O 복합 모듈 (8 DI + 8 DO).

v1.12 에서는 이 모듈을 2개(#1, #2) 사용한다. 구 코드의 4055(16DI)+4068(8relay)
모델을 대체한다.

출력은 stage → flush 2단계다. 상위(IO/컨트롤러)가 한 스캔 동안 여러 DO 를
stage 한 뒤 flush_do() 한 번으로 버스에 반영한다 (v1.12 §19 단일 출력 지점).
"""

from .modbus_hub import ModbusHub


class Adam4055:
    NUM_DI = 8
    NUM_DO = 8

    # Modbus 레지스터 주소 — TODO(verify-manual): ADAM-4055-C Modbus 매뉴얼로 확인.
    # (일반적으로 DI 는 discrete input, DO 는 coil 영역이나 실제 오프셋은 확인 필요)
    _DI_ADDR = 0x0000
    _DO_ADDR = 0x0000

    def __init__(self, hub: ModbusHub, unit_id: int, *, mock: bool = False, name: str = "") -> None:
        self.mock = mock
        self.unit_id = unit_id
        self.name = name or f"ADAM4055#{unit_id}"
        self._hub = hub
        self._do = [False] * self.NUM_DO        # 마지막으로 반영된 DO 상태
        self._staged = [False] * self.NUM_DO    # 아직 flush 전인 DO 스테이징
        self._mock_di = [False] * self.NUM_DI   # mock 입력 (시뮬레이터가 구동)

    # --- 입력 -------------------------------------------------------------
    def read_di(self) -> list[bool]:
        if self.mock:
            return list(self._mock_di)
        return self._hub.read_discrete_inputs(self.unit_id, self._DI_ADDR, self.NUM_DI)

    def read_do(self) -> list[bool]:
        """실제 반영된 DO 상태 (mock 은 내부 상태, 실 모드는 코일 리드백)."""
        if self.mock:
            return list(self._do)
        return self._hub.read_coils(self.unit_id, self._DO_ADDR, self.NUM_DO)

    # --- 출력 (stage → flush) --------------------------------------------
    def stage_do(self, channel: int, value: bool) -> None:
        self._staged[channel] = bool(value)

    def staged_do(self, channel: int) -> bool:
        return self._staged[channel]

    def flush_do(self) -> None:
        if not self.mock:
            self._hub.write_coils(self.unit_id, self._DO_ADDR, self._staged)
        self._do = list(self._staged)

    # --- 시뮬레이터용 (mock 전용) ----------------------------------------
    def set_mock_di(self, channel: int, value: bool) -> None:
        self._mock_di[channel] = bool(value)
