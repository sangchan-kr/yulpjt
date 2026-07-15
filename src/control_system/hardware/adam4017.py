"""ADAM-4017+-F — 8채널 아날로그 입력 모듈 (v1.12 §9).

AI-00 에 로드셀 트랜스미터 NCT-I420 의 4-20 mA 가 들어온다.
이 클래스는 mA 값만 돌려주고, kgf 환산은 LoadCell 이 담당한다.

mock 모드: 채널별로 고정 mA 를 설정(set_mock_ma)하거나, 미설정 채널은
느린 사인파로 흔들어 GUI 에서 값이 움직이는 걸 볼 수 있게 한다.
"""

import math
import time

from .modbus_hub import ModbusHub


class Adam4017:
    NUM_AI = 8

    # Modbus 주소/스케일 — TODO(verify-manual): ADAM-4017+ 매뉴얼로 확인.
    # 엔지니어링 단위(mA) vs raw count 읽기 모드도 입고 후 확정 (기본 mA 가정).
    _AI_ADDR = 0x0000
    _RAW_FULL = 0xFFFF          # raw count 만스케일 (실 모드 환산용, 확인 필요)
    _RAW_MA_SPAN = 20.0         # 0~20 mA 범위 가정

    def __init__(self, hub: ModbusHub, unit_id: int, *, mock: bool = False) -> None:
        self.mock = mock
        self.unit_id = unit_id
        self._hub = hub
        self._mock_ma: list[float | None] = [None] * self.NUM_AI
        self._t0 = time.monotonic()

    def read_ma(self, channel: int) -> float:
        if self.mock:
            return self._mock_read(channel)
        raw = self._hub.read_input_registers(self.unit_id, self._AI_ADDR + channel, 1)[0]
        return raw / self._RAW_FULL * self._RAW_MA_SPAN

    def read_all_ma(self) -> list[float]:
        return [self.read_ma(c) for c in range(self.NUM_AI)]

    # --- 시뮬레이터용 (mock 전용) ----------------------------------------
    def set_mock_ma(self, channel: int, ma: float | None) -> None:
        """채널 mA 고정. None 이면 데모 사인파로 되돌린다."""
        self._mock_ma[channel] = ma

    def set_mock_load_kgf(self, channel: int, kgf: float, full_scale_kgf: float) -> None:
        """하중(kgf)을 4-20 mA 로 환산해 mock 값으로 넣는다 (시뮬레이터 편의)."""
        ma = 4.0 + (kgf / full_scale_kgf) * 16.0
        self._mock_ma[channel] = max(4.0, min(20.0, ma))

    def _mock_read(self, channel: int) -> float:
        fixed = self._mock_ma[channel]
        if fixed is not None:
            return fixed
        if channel == 0:
            # 데모용: 0~약 300 kgf 를 오가는 4-20 mA 사인파
            t = time.monotonic() - self._t0
            frac = 0.5 + 0.5 * math.sin(t * 0.4)          # 0..1
            return 4.0 + frac * (16.0 * 0.3)              # 4 ~ 8.8 mA
        return 4.0
