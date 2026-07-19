"""제어 시스템 설정 (v1.12).

값을 바꾸는 방법은 두 가지다.

1. 이 파일의 ``Config`` 기본값을 직접 수정한다.
2. 환경변수로 덮어쓴다 (코드 수정 없이 현장/개발 전환용).
   ``Config.from_env()`` 가 아래 환경변수를 읽는다::

       MOCK_HW=1|0            # 1=모의 하드웨어(기본), 0=실 Modbus
       SERIAL_PORT=/dev/ttyUSB0   # Windows 개발이면 COM3 등
       BAUDRATE=9600
       FULL_SCALE_KGF=1000        # 로드셀 만용량(=앰프 20 mA 지점). 아래 게인표 참고
       LOAD_LIMIT_KGF=900

앰프 게인/스케일 세팅 방법은 ``AMP_GAIN_HELP`` 에 정리해 두었다.
``python -m control_system.config`` 를 실행하면 그 도움말을 출력한다.
"""

from dataclasses import dataclass, replace
from os import environ


# ---------------------------------------------------------------------------
# 로드셀 + 앰프(NCT-I420) 게인 세팅 도움말
# ---------------------------------------------------------------------------
# 나중에 로드셀/가압 범위를 바꿀 때 이 표를 보고 (1) 앰프 DIP 스위치와
# (2) loadcell_full_scale_kgf (= 환경변수 FULL_SCALE_KGF) 를 함께 맞춘다.
AMP_GAIN_HELP = """\
[로드셀/앰프 게인 세팅 — v1.12]

로드셀 : CSB-1T  (정격출력 2.0 mV/V, 용량 1 tf = 1000 kgf, 권장 여기전압 10V)
앰프   : NCT-I420, 출력 4-20 mA 모드 → 게인표의 'Vout1~5V (Iout4~20mA)' 열 사용
        그 열 값 = 출력이 20 mA(만스케일)에 도달하는 로드셀 입력 span(mV/V).

환산식 (소프트웨어) :
    raw_kgf = (mA - 4.0) / 16.0 * full_scale_kgf     # 4 mA=0, 20 mA=full_scale
    load    = (raw_kgf - zero_offset) * scale

■ 현재 채택값 (만용량 1000 kgf) — 최대 가압 1000 유지
    앰프 DIP SW1 : 1=OFF  2=OFF  3=OFF  4=ON   (내부 Gain 278)
    → 0 kgf = 4 mA, 1000 kgf = 20 mA
    → config: loadcell_full_scale_kgf = 1000.0

■ 나중에 실제 최대 가압이 1t보다 작아 분해능을 높이고 싶을 때
    필요 span = 2.0 * (최대하중 / 1000) mV/V, 그 이상인 가장 가까운 행 선택.
    앰프 DIP를 바꾸고 loadcell_full_scale_kgf 를 그 '20mA=하중' 값으로 맞춘다.

    | Iout4~20mA 열(mV/V) | DIP 1-2-3-4       | 20 mA = 하중 | Gain |
    |--------------------|-------------------|-------------|------|
    | 2.0                | OFF OFF OFF ON    | 1000 kgf ★  | 278  |
    | 1.0                | OFF ON  OFF OFF   |  500 kgf    | 556  |
    | 0.85               | OFF OFF ON  ON    |  425 kgf    | 651  |
    | 0.65               | OFF ON  OFF ON    |  325 kgf    | 838  |
    | 0.6                | OFF ON  ON  OFF   |  300 kgf    | 916  |
    | 0.5                | ON  OFF OFF OFF   |  250 kgf    | 1112 |
    | 0.4                | ON  OFF OFF ON    |  200 kgf    | 1394 |
    | 0.32               | ON  OFF ON  ON    |  160 kgf    | 1763 |
    | 0.25               | ON  ON  ON  ON    |  125 kgf    | 2322 |
    (★ = 현재 채택)

'압력' 으로 표시하려면 하중(kgf)을 접촉 면적으로 나눈다 (압력 = 힘/면적).
접촉 면적이 정해지면 kgf → MPa/bar 변환을 추가한다. 기본은 하중(kgf) 표시.
"""


@dataclass(frozen=True)
class Config:
    # --- 모드 -------------------------------------------------------------
    mock_hardware: bool = True          # True=모의, False=실 Modbus (MOCK_HW)

    # --- RS-485 / Modbus 버스 (단일 버스에 3개 노드) ----------------------
    serial_port: str = "/dev/ttyUSB0"   # Windows 개발 시 "COM3" 등
    baudrate: int = 9600                # 9600 또는 19200 (v1.12 §4)
    parity: str = "N"                   # "N" | "E"
    stopbits: int = 1
    bytesize: int = 8
    timeout_ms: int = 400               # Modbus 응답 타임아웃 (300~500)
    retries: int = 2                    # 재시도 (1~3)
    poll_ms: int = 100                  # 폴링 주기 (50~200)

    # --- 노드 ID (v1.12 §4) ----------------------------------------------
    node_adam1: int = 1                 # ADAM-4055-C #1 (프레스/스위치/타워)
    node_adam2: int = 2                 # ADAM-4055-C #2 (진공 이젝터/예비)
    node_adam4017: int = 3              # ADAM-4017+-F (아날로그 입력)

    # --- 로드셀 / 아날로그 (v1.12 §9, AMP_GAIN_HELP 참고) ------------------
    loadcell_ai_channel: int = 0        # ADAM-4017+ AI-00
    loadcell_full_scale_kgf: float = 1000.0   # 앰프 20 mA 지점 = 만용량
    loadcell_calibration_path: str = "calibration.json"
    load_limit_kgf: float = 500.0       # LOAD_OVER_LIMIT 알람 임계 (시운전값)

    # --- 자동 가압 시퀀스 타이밍 (v1.12 §12, HMI §10) --------------------
    down_dwell_ms: int = 2000           # 하강 유지 시간
    up_dwell_ms: int = 1000             # 상승 유지 시간
    down_timeout_ms: int = 5000         # 하강 위치 도달 타임아웃 (이동시간 다를 수 있어 분리)
    up_timeout_ms: int = 5000           # 상승 위치 도달 타임아웃
    target_count: int = 500             # 목표 반복 횟수

    # --- 진공 (수동, HMI 토글 — 완전 분리, 모든 진공 알람은 논블로킹) -----
    vacuum_confirm_timeout_ms: int = 2000  # Vacuum ON 후 OK 미도달 → VACUUM_NOT_REACHED(경고)
    vacuum_residual_ms: int = 3000         # Vacuum OFF 인데 OK 지속 → VACUUM_SIGNAL_ABNORMAL(경고)
    # blow-off 는 유지보수 hold-to-run 전용 (메인 화면/자동 시퀀스에서 미사용)
    blowoff_delay_ms: int = 80          # 유지보수 시험: 흡착 OFF 후 blow-off 시작까지
    blowoff_hold_ms: int = 300          # 유지보수 시험: blow-off 최대 유지

    # --- 입력 논리 반전 (NPN 등, v1.12 §7.2) ------------------------------
    invert_vacuum_ok: bool = False      # ZK2A NPN 스위치 결선 검증 후 결정 (Phase D)

    # ---------------------------------------------------------------------
    @classmethod
    def from_env(cls) -> "Config":
        """환경변수로 기본값을 덮어쓴 Config 를 만든다."""
        cfg = cls()
        overrides: dict = {}
        if "MOCK_HW" in environ:
            overrides["mock_hardware"] = environ["MOCK_HW"].strip() == "1"
        if "SERIAL_PORT" in environ:
            overrides["serial_port"] = environ["SERIAL_PORT"]
        if "BAUDRATE" in environ:
            overrides["baudrate"] = int(environ["BAUDRATE"])
        if "FULL_SCALE_KGF" in environ:
            overrides["loadcell_full_scale_kgf"] = float(environ["FULL_SCALE_KGF"])
        if "LOAD_LIMIT_KGF" in environ:
            overrides["load_limit_kgf"] = float(environ["LOAD_LIMIT_KGF"])
        return replace(cfg, **overrides) if overrides else cfg


def print_help() -> None:
    print(AMP_GAIN_HELP)


if __name__ == "__main__":
    print_help()
