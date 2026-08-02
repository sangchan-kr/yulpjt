"""로드셀 하중 환산기 (v1.12 §9).

더 이상 하드웨어 드라이버가 아니다. ADAM-4017+ AI-00 의 4-20 mA 를 받아
하중(kgf)으로 환산한다. HX711/GPIO 는 v1.12 에서 제거되었다.

    raw_kgf = (mA - 4.0) / 16.0 * full_scale_kgf     # 4 mA=0, 20 mA=full_scale
    load    = (raw_kgf - zero_offset) * scale

full_scale_kgf(=앰프 20 mA 지점)와 앰프 게인 세팅은 config.AMP_GAIN_HELP 참고.
zero_offset / scale 은 calibration 파일에 저장/복원한다.
"""

import json
import os


class LoadCell:
    # 4 mA 미만이면 단선/트랜스미터 이상으로 본다 (센서 유효성).
    WIRE_BREAK_MA = 3.5

    def __init__(
        self,
        ai_module,
        channel: int,
        full_scale_kgf: float,
        calibration_path: str,
        *,
        zero_offset: float = 0.0,
        scale: float = 1.0,
    ) -> None:
        self._ai = ai_module
        self.channel = channel
        self.full_scale_kgf = full_scale_kgf
        self.calibration_path = calibration_path
        self.zero_offset = zero_offset
        self.scale = scale
        self.load_calibration()

    # --- 순수 변환 (이미 읽은 mA 로부터, 시리얼 접근 없음) ----------------
    def raw_kgf_from_ma(self, ma: float) -> float:
        return (ma - 4.0) / 16.0 * self.full_scale_kgf

    def kgf_from_ma(self, ma: float) -> float:
        return (self.raw_kgf_from_ma(ma) - self.zero_offset) * self.scale

    def valid_from_ma(self, ma: float) -> bool:
        return ma >= self.WIRE_BREAK_MA

    # --- 읽기 (라이브 시리얼) — 툴/캘리브레이션용. 스캔 루프는 캐시값을 쓴다 -----
    def read_ma(self) -> float:
        return self._ai.read_ma(self.channel)

    def current_valid(self) -> bool:
        """4-20 mA 루프가 살아있는지 (단선 감지)."""
        return self.valid_from_ma(self.read_ma())

    def read_raw_kgf(self) -> float:
        return self.raw_kgf_from_ma(self.read_ma())

    def read_kgf(self) -> float:
        return self.kgf_from_ma(self.read_ma())

    # --- 캘리브레이션 -----------------------------------------------------
    def tare(self) -> None:
        """현재 하중을 영점으로 (무부하 상태에서 호출)."""
        self.zero_offset = self.read_raw_kgf()
        self.save_calibration()

    def set_scale(self, scale: float) -> None:
        self.scale = scale
        self.save_calibration()

    def calibrate_span(self, known_kgf: float) -> bool:
        """기준 하중(known_kgf)을 올린 상태에서 호출 → scale 재계산.

        영점(zero_offset) 적용 후 측정값 대비 기준값으로 scale 을 맞춘다.
        측정값이 0 이거나 기준값이 0 이하면 무시(False).
        """
        measured = self.read_raw_kgf() - self.zero_offset
        if measured <= 0 or known_kgf <= 0:
            return False
        self.scale = known_kgf / measured
        self.save_calibration()
        return True

    def load_calibration(self) -> None:
        if not os.path.exists(self.calibration_path):
            return
        try:
            with open(self.calibration_path, encoding="utf-8") as f:
                data = json.load(f)
            self.zero_offset = float(data.get("zero_offset", self.zero_offset))
            self.scale = float(data.get("scale", self.scale))
        except (OSError, ValueError, json.JSONDecodeError):
            # 캘리브 파일이 깨졌으면 기본값 유지 (조용히 무시).
            pass

    def save_calibration(self) -> None:
        data = {
            "zero_offset": self.zero_offset,
            "scale": self.scale,
            "full_scale_kgf": self.full_scale_kgf,
        }
        with open(self.calibration_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
