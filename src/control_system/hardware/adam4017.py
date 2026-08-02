"""ADAM-4017+-F — 8채널 아날로그 입력 모듈, Advantech ASCII(DCON).

AI-00 에 로드셀 트랜스미터(4-20 mA)가 들어온다. 이 클래스는 mA 값만 돌려주고
kgf 환산은 LoadCell 이 담당한다.

DCON 명령:
  #AA        → 전 채널 값 ">±dd.ddd±dd.ddd..." (현재 설정 데이터포맷)
  #AAN       → N 채널 값 ">±dd.ddd"

전류 읽기 방식(현장 설정):
  채널 0 은 하드웨어 점퍼로 전류(4-20mA) 모드지만 소프트웨어 range 가 ±10V 라,
  모듈이 내부 120Ω 전류저항 양단 '전압(V)'을 반환한다 → mA = V / 120Ω * 1000.
  (INIT 모드에서 range 07(4-20mA)로 바꾸면 모듈이 mA 를 직접 반환하므로 그때는
   CURRENT_DIRECT=True 로 바꾼다.)

mock 모드: 채널별 고정 mA(set_mock_ma) 또는 데모 사인파.
"""

import math
import re
import time

from .modbus_hub import AdamCommError, AdamSerialBus

_VALUE_RE = re.compile(r"[+-]\d+(?:\.\d+)?")


class Adam4017:
    NUM_AI = 8

    CURRENT_DIRECT = False      # False: ±10V 전압읽기+120Ω 환산, True: range07 mA 직접
    _SENSE_OHM = 120.0          # ADAM-4017+ 내부 전류 감지 저항

    def __init__(self, hub: AdamSerialBus, unit_id: int, *, mock: bool = False) -> None:
        self.mock = mock
        self.unit_id = unit_id
        self._hub = hub
        self._mock_ma: list[float | None] = [None] * self.NUM_AI
        self._t0 = time.monotonic()

    def _to_ma(self, value: float) -> float:
        return value if self.CURRENT_DIRECT else (value / self._SENSE_OHM * 1000.0)

    def read_ma(self, channel: int) -> float:
        if self.mock:
            return self._mock_read(channel)
        r = self._hub.command(f"#{self.unit_id:02X}{channel}")   # #AAN
        m = _VALUE_RE.search(r)
        if not m:
            raise AdamCommError(f"AI#{self.unit_id} ch{channel} 응답 이상: {r!r}")
        return self._to_ma(float(m.group()))

    def read_all_ma(self) -> list[float]:
        if self.mock:
            return [self._mock_read(c) for c in range(self.NUM_AI)]
        r = self._hub.command(f"#{self.unit_id:02X}")            # #AA
        vals = _VALUE_RE.findall(r)
        if len(vals) < self.NUM_AI:
            raise AdamCommError(f"AI#{self.unit_id} 전채널 응답 이상: {r!r}")
        return [self._to_ma(float(v)) for v in vals[: self.NUM_AI]]

    # --- 시뮬레이터용 (mock 전용) ----------------------------------------
    def set_mock_ma(self, channel: int, ma: float | None) -> None:
        self._mock_ma[channel] = ma

    def set_mock_load_kgf(self, channel: int, kgf: float, full_scale_kgf: float) -> None:
        ma = 4.0 + (kgf / full_scale_kgf) * 16.0
        self._mock_ma[channel] = max(4.0, min(20.0, ma))

    def _mock_read(self, channel: int) -> float:
        fixed = self._mock_ma[channel]
        if fixed is not None:
            return fixed
        if channel == 0:
            t = time.monotonic() - self._t0
            frac = 0.5 + 0.5 * math.sin(t * 0.4)
            return 4.0 + frac * (16.0 * 0.3)
        return 4.0
