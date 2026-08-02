"""ADAM-4055-C — 절연 디지털 I/O 복합 모듈 (8 DI + 8 DO), Advantech ASCII(DCON).

v1.12 에서 2개(#1, #2) 사용. 출력은 stage → flush 2단계(§19 단일 출력 지점).

DCON 명령:
  읽기  $AA6           → 응답 !(DO)(DI)00   (DO 피드백 2hex, DI 2hex, bit0=채널0)
  쓰기  #AA00(data)    → 전체 8채널 DO 를 한 바이트로. 응답 '>' 성공 / '?' 오류
"""

from .modbus_hub import AdamCommError, AdamSerialBus


class Adam4055:
    NUM_DI = 8
    NUM_DO = 8

    def __init__(self, hub: AdamSerialBus, unit_id: int, *, mock: bool = False, name: str = "") -> None:
        self.mock = mock
        self.unit_id = unit_id
        self.name = name or f"ADAM4055#{unit_id}"
        self._hub = hub
        self._do = [False] * self.NUM_DO        # 마지막으로 반영된 DO 상태
        self._staged = [False] * self.NUM_DO    # 아직 flush 전인 DO 스테이징
        self._mock_di = [False] * self.NUM_DI   # mock 입력 (시뮬레이터가 구동)
        self._hw_di: list[bool] | None = None   # 실 모드 캐시 ($AA6)
        self._hw_do: list[bool] | None = None

    # --- 입력 -------------------------------------------------------------
    def read_di(self) -> list[bool]:
        if self.mock:
            return list(self._mock_di)
        self._refresh_from_hw()
        return list(self._hw_di)

    def read_do(self) -> list[bool]:
        """실제 반영된 DO 상태 (mock=내부 상태, 실 모드=모듈 피드백)."""
        if self.mock:
            return list(self._do)
        if self._hw_do is None:
            self._refresh_from_hw()
        return list(self._hw_do)

    def cached_do(self) -> list[bool]:
        """마지막으로 반영된 DO 상태(추가 폴링 없음). 상태표시용."""
        if self.mock:
            return list(self._do)
        return list(self._hw_do) if self._hw_do is not None else list(self._do)

    def _refresh_from_hw(self) -> None:
        """$AA6 한 번 읽어 DI/DO 를 함께 캐시한다."""
        r = self._hub.command(f"${self.unit_id:02X}6")
        if not r.startswith("!") or len(r) < 5:
            raise AdamCommError(f"{self.name} $AA6 응답 이상: {r!r}")
        do_byte = int(r[1:3], 16)      # 첫 필드 = DO 피드백
        di_byte = int(r[3:5], 16)      # 둘째 필드 = DI
        self._hw_do = [bool(do_byte >> ch & 1) for ch in range(self.NUM_DO)]
        self._hw_di = [bool(di_byte >> ch & 1) for ch in range(self.NUM_DI)]

    # --- 출력 (stage → flush) --------------------------------------------
    def stage_do(self, channel: int, value: bool) -> None:
        self._staged[channel] = bool(value)

    def staged_do(self, channel: int) -> bool:
        return self._staged[channel]

    def flush_do(self) -> None:
        if not self.mock:
            byte = 0
            for ch in range(self.NUM_DO):
                if self._staged[ch]:
                    byte |= (1 << ch)
            resp = self._hub.command(f"#{self.unit_id:02X}00{byte:02X}")
            if not resp.startswith(">"):
                raise AdamCommError(f"{self.name} DO 쓰기 실패: {resp!r}")
            self._hw_do = list(self._staged)   # 방금 쓴 값으로 피드백 캐시 갱신
        self._do = list(self._staged)

    # --- 시뮬레이터용 (mock 전용) ----------------------------------------
    def set_mock_di(self, channel: int, value: bool) -> None:
        self._mock_di[channel] = bool(value)
