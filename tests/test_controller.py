"""Phase B/C2 상태머신 테스트 (mock 하드웨어 + 주입 clock + 가상 실린더 플랜트).

pytest 로도, `python tests/test_controller.py` 로도 실행된다.
"""

import os
import sys
import tempfile
from dataclasses import replace

_SRC = os.path.join(os.path.dirname(__file__), "..", "src")
if _SRC not in sys.path:
    sys.path.insert(0, os.path.abspath(_SRC))

from control_system.config import Config
from control_system.core.controller import Controller
from control_system.core.safety import apply_output_safety
from control_system.core.states import Alarm, Outputs, State
from control_system.hardware.adam4017 import Adam4017
from control_system.hardware.adam4055 import Adam4055
from control_system.hardware.loadcell import LoadCell
from control_system.hardware.signals import DI1, DI2, DO1, DO2, IO


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


def _build(**over):
    cfg = replace(
        Config(),
        target_count=over.pop("target_count", 2),
        down_timeout_ms=over.pop("down_timeout_ms", 1000),
        up_timeout_ms=over.pop("up_timeout_ms", 1000),
        down_dwell_ms=over.pop("down_dwell_ms", 100),
        up_dwell_ms=over.pop("up_dwell_ms", 100),
        vacuum_confirm_timeout_ms=over.pop("vacuum_confirm_timeout_ms", 500),
        vacuum_residual_ms=over.pop("vacuum_residual_ms", 500),
        blowoff_delay_ms=over.pop("blowoff_delay_ms", 80),
        blowoff_hold_ms=over.pop("blowoff_hold_ms", 150),
        **over,
    )
    a1 = Adam4055(None, 1, mock=True)
    a2 = Adam4055(None, 2, mock=True)
    ai = Adam4017(None, 3, mock=True)
    ai.set_mock_ma(0, 4.0)
    io = IO(a1, a2, ai)
    tmp = os.path.join(tempfile.gettempdir(), "cal_ctrl.json")
    if os.path.exists(tmp):
        os.remove(tmp)
    lc = LoadCell(ai, 0, cfg.loadcell_full_scale_kgf, tmp)
    ctrl = Controller(cfg, io, lc, clock=Clock())
    return ctrl, a1, a2, ai, ctrl._clock


def _di(module, sig, val):
    module.set_mock_di(int(sig), val)


def _plant(ctrl, a1):
    if ctrl.out.valve_down:
        _di(a1, DI1.CYL_DOWN_POS, True); _di(a1, DI1.CYL_UP_POS, False)
    elif ctrl.out.valve_up:
        _di(a1, DI1.CYL_UP_POS, True); _di(a1, DI1.CYL_DOWN_POS, False)


# ---------------------------------------------------------------- safety unit
def test_safety_sol_disable_kills_actuators():
    o = Outputs(valve_down=True, vacuum_on=True)
    apply_output_safety(o, sol_enable_ok=False)
    assert not o.valve_down and not o.vacuum_on


def test_safety_valve_interlock_blocking():
    o = Outputs(valve_down=True, valve_up=True)
    blocking, warnings = apply_output_safety(o, sol_enable_ok=True)
    assert not o.valve_down and not o.valve_up
    assert Alarm.VALVE_INTERLOCK in blocking


def test_safety_vacuum_blowoff_is_warning_not_blocking():
    o = Outputs(vacuum_on=True, blow_off_on=True)
    blocking, warnings = apply_output_safety(o, sol_enable_ok=True)
    assert not o.vacuum_on and not o.blow_off_on
    assert Alarm.VACUUM_BLOWOFF_INTERLOCK in warnings
    assert not blocking                       # 진공 인터록은 블로킹 아님


def test_safety_adam2_disconnect_kills_vacuum():
    o = Outputs(vacuum_on=True, valve_down=True)
    apply_output_safety(o, sol_enable_ok=True, adam2_connected=False)
    assert not o.vacuum_on                    # 진공은 OFF
    assert o.valve_down                        # 밸브(ADAM #1)는 영향 없음


# ---------------------------------------------------------------- boot / mode
def test_boot_to_idle_auto():
    ctrl, a1, a2, ai, clk = _build()
    _di(a1, DI1.MODE_AUTO, True)
    _di(a1, DI1.SOL_ENABLE_OK, True)
    ctrl.scan()
    assert ctrl.state is State.AUTO_IDLE


def test_mode_switch_when_idle():
    ctrl, a1, a2, ai, clk = _build()
    _di(a1, DI1.SOL_ENABLE_OK, True)
    _di(a1, DI1.MODE_AUTO, False)
    ctrl.scan()
    assert ctrl.state is State.MANUAL_IDLE
    _di(a1, DI1.MODE_AUTO, True)
    ctrl.scan()
    assert ctrl.state is State.AUTO_IDLE


# ---------------------------------------------------------------- safety stop
def test_safety_stop_latch_and_reset():
    ctrl, a1, a2, ai, clk = _build()
    _di(a1, DI1.MODE_AUTO, True)
    _di(a1, DI1.SOL_ENABLE_OK, True)
    ctrl.scan()
    _di(a1, DI1.SOL_ENABLE_OK, False)
    ctrl.scan()
    assert ctrl.state is State.SAFETY_STOP
    _di(a1, DI1.SOL_ENABLE_OK, True)
    ctrl.scan()
    assert ctrl.state is State.SAFETY_STOP     # 복귀만으로는 안 됨
    ctrl.cmd_safety_reset()
    ctrl.scan()
    assert ctrl.state is State.AUTO_IDLE


def test_safety_stop_latches_vacuum_off_no_restore():
    ctrl, a1, a2, ai, clk = _build()
    _di(a1, DI1.SOL_ENABLE_OK, True)
    _di(a1, DI1.MODE_AUTO, False)
    ctrl.scan()
    ctrl.set_vacuum(True)
    ctrl.scan()
    assert ctrl.out.vacuum_on is True
    _di(a1, DI1.SOL_ENABLE_OK, False)          # Safety Stop
    ctrl.scan()
    assert ctrl.state is State.SAFETY_STOP
    assert ctrl.vacuum_command is False        # 래치 해제
    assert ctrl.out.vacuum_on is False
    _di(a1, DI1.SOL_ENABLE_OK, True)
    ctrl.cmd_safety_reset()
    ctrl.scan()
    assert ctrl.vacuum_command is False        # 자동 복원 금지 — 다시 눌러야 함
    assert ctrl.out.vacuum_on is False


# ---------------------------------------------------------------- manual
def test_manual_up_down_and_conflict():
    ctrl, a1, a2, ai, clk = _build()
    _di(a1, DI1.SOL_ENABLE_OK, True)
    _di(a1, DI1.MODE_AUTO, False)
    ctrl.scan()
    _di(a1, DI1.MANUAL_UP_PB, True)
    ctrl.scan()
    assert ctrl.out.valve_up and not ctrl.out.valve_down
    assert a1.read_do()[int(DO1.K_VALVE_UP)] is True
    _di(a1, DI1.MANUAL_UP_PB, False)
    _di(a1, DI1.MANUAL_DOWN_PB, True)
    ctrl.scan()
    assert ctrl.out.valve_down and not ctrl.out.valve_up
    _di(a1, DI1.MANUAL_UP_PB, True)
    ctrl.scan()
    assert not ctrl.out.valve_up and not ctrl.out.valve_down
    assert Alarm.MANUAL_CONFLICT in ctrl.alarms


def test_manual_stops_at_position_sensor():
    """수동: 위치 센서에 닿으면 해당 방향 밸브 정지. 하강은 센서 미도달이어도 에러 아님."""
    ctrl, a1, a2, ai, clk = _build()
    _di(a1, DI1.SOL_ENABLE_OK, True)
    _di(a1, DI1.MODE_AUTO, False)
    ctrl.scan()
    # 상승: 아직 상승위치 미도달 → 상승
    _di(a1, DI1.MANUAL_UP_PB, True)
    ctrl.scan()
    assert ctrl.out.valve_up
    # 상승위치 센서 도달 → 버튼 계속 눌러도 정지
    _di(a1, DI1.CYL_UP_POS, True)
    ctrl.scan()
    assert not ctrl.out.valve_up
    _di(a1, DI1.MANUAL_UP_PB, False)
    _di(a1, DI1.CYL_UP_POS, False)
    # 하강: 하강위치 미도달(샘플에 막힘) → 계속 가압, 에러/알람 없음
    _di(a1, DI1.MANUAL_DOWN_PB, True)
    for _ in range(20):
        clk.advance(0.1)
        ctrl.scan()
    assert ctrl.out.valve_down
    assert ctrl.state is State.MANUAL_IDLE
    assert not ctrl.alarms                        # 센서 미도달이 에러가 되면 안 됨
    # 하강위치 센서 도달 → 정지
    _di(a1, DI1.CYL_DOWN_POS, True)
    ctrl.scan()
    assert not ctrl.out.valve_down


def test_buzzer_sounds_until_safety_reset():
    """SAFETY_STOP 부저는 sol 복귀만으로 꺼지지 않고, 안전 복귀를 눌러야 멈춘다."""
    ctrl, a1, a2, ai, clk = _build()
    _di(a1, DI1.MODE_AUTO, False)
    _di(a1, DI1.SOL_ENABLE_OK, False)
    ctrl.scan()                                  # t=0, fast 위상
    assert ctrl.state is State.SAFETY_STOP
    assert ctrl.out.buzzer is True               # 부저 ON
    _di(a1, DI1.SOL_ENABLE_OK, True)             # 복귀 조건 충족(그래도 SAFETY_STOP 유지)
    ctrl.scan()
    assert ctrl.state is State.SAFETY_STOP
    assert ctrl.out.buzzer is True               # 아직 안전 복귀 전 → 부저 계속
    ctrl.cmd_safety_reset()
    ctrl.scan()
    assert ctrl.state is State.MANUAL_IDLE
    assert ctrl.out.buzzer is False              # 안전 복귀 후 부저 OFF


def test_buzzer_mute_and_auto_rearm():
    """부저 정지 버튼 → 이번 이벤트 음소거. 알람 해소되면 자동 해제(다음 이벤트 재알람)."""
    ctrl, a1, a2, ai, clk = _build()
    _di(a1, DI1.MODE_AUTO, False)
    _di(a1, DI1.SOL_ENABLE_OK, False)
    ctrl.scan()
    assert ctrl.out.buzzer is True
    ctrl.cmd_buzzer_mute(); ctrl.scan()
    assert ctrl.out.buzzer is False              # 음소거
    _di(a1, DI1.SOL_ENABLE_OK, True)
    ctrl.cmd_safety_reset(); ctrl.scan()          # 복귀 → 알람 해소 → 음소거 자동 해제
    assert ctrl.state is State.MANUAL_IDLE
    _di(a1, DI1.SOL_ENABLE_OK, False)
    ctrl.scan()                                   # 새 안전정지
    assert ctrl.out.buzzer is True               # 다시 울림


def test_manual_blocked_when_sol_off():
    ctrl, a1, a2, ai, clk = _build()
    _di(a1, DI1.SOL_ENABLE_OK, False)
    _di(a1, DI1.MODE_AUTO, False)
    ctrl.scan()
    _di(a1, DI1.MANUAL_UP_PB, True)
    ctrl.scan()
    assert not ctrl.out.valve_up


# ---------------------------------------------------------------- auto cycle
def test_auto_full_cycle_reaches_complete():
    ctrl, a1, a2, ai, clk = _build(target_count=2)
    _di(a1, DI1.SOL_ENABLE_OK, True)
    _di(a1, DI1.MODE_AUTO, True)
    ctrl.scan()
    _di(a1, DI1.AUTO_START_PB, True); ctrl.scan(); _di(a1, DI1.AUTO_START_PB, False)
    seen_down = seen_up = False
    for _ in range(400):
        clk.advance(0.03); ctrl.scan(); _plant(ctrl, a1)
        seen_down = seen_down or ctrl.out.valve_down
        seen_up = seen_up or ctrl.out.valve_up
        if ctrl.state in (State.AUTO_COMPLETE, State.ERROR):
            break
    assert ctrl.state is State.AUTO_COMPLETE
    assert ctrl.count == 2
    assert seen_down and seen_up
    assert not ctrl.alarms


def test_auto_restart_after_complete():
    # 완료(AUTO_COMPLETE) 상태에서 Auto Start 재입력 → 카운트 리셋 + 정해진 횟수 재반복.
    ctrl, a1, a2, ai, clk = _build(target_count=2)
    _di(a1, DI1.SOL_ENABLE_OK, True)
    _di(a1, DI1.MODE_AUTO, True)
    ctrl.scan()

    def run_to_complete():
        for _ in range(400):
            clk.advance(0.03); ctrl.scan(); _plant(ctrl, a1)
            if ctrl.state in (State.AUTO_COMPLETE, State.ERROR):
                return

    # 1회차
    _di(a1, DI1.AUTO_START_PB, True); ctrl.scan(); _di(a1, DI1.AUTO_START_PB, False)
    run_to_complete()
    assert ctrl.state is State.AUTO_COMPLETE and ctrl.count == 2

    # 완료 상태에서 재입력 → 즉시 카운트 0, 재시작
    _di(a1, DI1.AUTO_START_PB, True); ctrl.scan(); _di(a1, DI1.AUTO_START_PB, False)
    assert ctrl.state is State.AUTO_PRECHECK
    assert ctrl.count == 0

    # 2회차도 완주
    run_to_complete()
    assert ctrl.state is State.AUTO_COMPLETE and ctrl.count == 2


def test_auto_complete_to_manual_on_selector():
    # 완료 상태에서 셀렉터를 MANUAL 로 → 수동 대기로 전환.
    ctrl, a1, a2, ai, clk = _build(target_count=1, down_dwell_ms=20, up_dwell_ms=20)
    _di(a1, DI1.SOL_ENABLE_OK, True)
    _di(a1, DI1.MODE_AUTO, True)
    ctrl.scan()
    _di(a1, DI1.AUTO_START_PB, True); ctrl.scan(); _di(a1, DI1.AUTO_START_PB, False)
    for _ in range(400):
        clk.advance(0.03); ctrl.scan(); _plant(ctrl, a1)
        if ctrl.state in (State.AUTO_COMPLETE, State.ERROR):
            break
    assert ctrl.state is State.AUTO_COMPLETE
    _di(a1, DI1.MODE_AUTO, False)
    ctrl.scan()
    assert ctrl.state is State.MANUAL_IDLE


def test_restart_after_safety_recovery_resets_count():
    # 완료(카운트=목표) → 안전정지 → 복귀(AUTO_IDLE, 카운트 유지) → Auto Start 하면
    # 새 배치로 리셋되어 목표에서 멈춰야 한다 (목표+1 로 넘어가지 않음).
    ctrl, a1, a2, ai, clk = _build(target_count=3, down_dwell_ms=20, up_dwell_ms=20)
    _di(a1, DI1.SOL_ENABLE_OK, True); _di(a1, DI1.MODE_AUTO, True); ctrl.scan()

    def start_and_finish():
        _di(a1, DI1.AUTO_START_PB, True); ctrl.scan(); _di(a1, DI1.AUTO_START_PB, False)
        for _ in range(500):
            clk.advance(0.02); ctrl.scan(); _plant(ctrl, a1)
            if ctrl.state in (State.AUTO_COMPLETE, State.ERROR):
                return

    start_and_finish()
    assert ctrl.state is State.AUTO_COMPLETE and ctrl.count == 3
    _di(a1, DI1.SOL_ENABLE_OK, False); ctrl.scan()
    assert ctrl.state is State.SAFETY_STOP
    _di(a1, DI1.SOL_ENABLE_OK, True); ctrl.cmd_safety_reset(); ctrl.scan()
    assert ctrl.state is State.AUTO_IDLE and ctrl.count == 3
    start_and_finish()
    assert ctrl.state is State.AUTO_COMPLETE
    assert ctrl.count == 3            # 6 이 아니라 3


def test_load_over_limit_during_up_phase():
    # 하중 상한 초과는 하강뿐 아니라 자동 어느 단계(상승 유지 등)에서도 즉시 폴트.
    ctrl, a1, a2, ai, clk = _build(target_count=3, load_limit_kgf=100.0,
                                   down_dwell_ms=20, up_dwell_ms=300)
    _di(a1, DI1.SOL_ENABLE_OK, True); _di(a1, DI1.MODE_AUTO, True); ctrl.scan()
    _di(a1, DI1.AUTO_START_PB, True); ctrl.scan(); _di(a1, DI1.AUTO_START_PB, False)
    injected = False
    for _ in range(500):
        clk.advance(0.02); ctrl.scan(); _plant(ctrl, a1)
        if ctrl.state is State.AUTO_DWELL_UP and not injected:
            ai.set_mock_load_kgf(0, 500.0, ctrl.cfg.loadcell_full_scale_kgf); injected = True
        if ctrl.state in (State.ERROR, State.AUTO_COMPLETE):
            break
    assert injected
    assert ctrl.state is State.ERROR
    assert Alarm.LOAD_OVER_LIMIT in ctrl.alarms


def test_auto_down_no_sensor_proceeds_no_error():
    """자동 하강: 샘플 크기로 하강센서 미도달이어도 에러 없이 이동시간 후 다웰로 진행.

    (시스템 구성상 하강 센서가 동작 안 할 수 있음 — 타임아웃을 폴트로 처리하면 안 됨.
    과가압은 LOAD_OVER_LIMIT 이 보호.)
    """
    ctrl, a1, a2, ai, clk = _build(down_timeout_ms=200, down_dwell_ms=50, up_dwell_ms=20)
    _di(a1, DI1.SOL_ENABLE_OK, True)
    _di(a1, DI1.MODE_AUTO, True)
    ctrl.scan()
    _di(a1, DI1.AUTO_START_PB, True); ctrl.scan(); _di(a1, DI1.AUTO_START_PB, False)
    reached_dwell = False
    for _ in range(100):
        clk.advance(0.03); ctrl.scan()
        # 하강 위치센서는 절대 주지 않음(샘플에 막힘). 상승만 정상 도달시켜 사이클 진행.
        _di(a1, DI1.CYL_UP_POS, bool(ctrl.out.valve_up))
        if ctrl.state is State.AUTO_DWELL_DOWN:
            reached_dwell = True
        if ctrl.state is State.ERROR:
            break
    assert reached_dwell                        # 하강센서 없이도 다웰로 진행
    assert ctrl.state is not State.ERROR
    assert Alarm.DOWN_TIMEOUT not in ctrl.alarms


def test_auto_down_load_detect():
    """하강 하중 도달 사용 시: 로드셀이 기준값 이상이면 위치센서 없이도 다웰 진입."""
    ctrl, a1, a2, ai, clk = _build(down_timeout_ms=5000, down_dwell_ms=50)
    ctrl.settings.down_load_detect = True
    ctrl.settings.down_load_threshold_kgf = 300.0
    _di(a1, DI1.SOL_ENABLE_OK, True)
    _di(a1, DI1.MODE_AUTO, True)
    ai.set_mock_ma(0, 4.0)                       # ~0 kgf
    ctrl.scan()
    _di(a1, DI1.AUTO_START_PB, True); ctrl.scan(); _di(a1, DI1.AUTO_START_PB, False)
    for _ in range(6):
        clk.advance(0.03); ctrl.scan()
        if ctrl.out.valve_down:                 # 실제 하강 밸브가 켜질 때까지 진행
            break
    assert ctrl.state is State.AUTO_MOVE_DOWN and ctrl.out.valve_down
    clk.advance(0.03); ctrl.scan()
    assert ctrl.state is State.AUTO_MOVE_DOWN    # 하중 낮음 → 계속 하강
    ai.set_mock_ma(0, 4.0 + 16.0 * 0.4)          # 400 kgf ≥ 기준 300
    clk.advance(0.03); ctrl.scan()
    assert ctrl.state is State.AUTO_DWELL_DOWN    # 하중 도달 → 다웰 진입
    assert not ctrl.alarms                        # 에러 아님


def test_auto_up_short_stroke_no_error():
    """자동 상승: 스트로크를 줄여 상승센서 미도달이어도 시간 경과로 다웰→진행(에러 아님).

    (교체 위치 _run_manual_move_up 은 센서까지 가야 하므로 거기선 UP_TIMEOUT 유지 — 별도 테스트.)
    """
    ctrl, a1, a2, ai, clk = _build(down_timeout_ms=2000, up_timeout_ms=150,
                                   down_dwell_ms=20, up_dwell_ms=20, target_count=1)
    _di(a1, DI1.SOL_ENABLE_OK, True)
    _di(a1, DI1.MODE_AUTO, True)
    ctrl.scan()
    _di(a1, DI1.AUTO_START_PB, True); ctrl.scan(); _di(a1, DI1.AUTO_START_PB, False)
    for _ in range(300):
        clk.advance(0.03); ctrl.scan()
        _di(a1, DI1.CYL_DOWN_POS, bool(ctrl.out.valve_down))   # 하강만 즉시 도달 시뮬
        # 자동 사이클 상승엔 위치센서 안 줌(짧은 스트로크). 완료 후 교체 이동에서만 도달 시뮬.
        if ctrl.state is State.AUTO_EXCHANGE_UP and ctrl.out.valve_up:
            _di(a1, DI1.CYL_UP_POS, True)
        if ctrl.state in (State.AUTO_COMPLETE, State.ERROR):
            break
    assert ctrl.state is State.AUTO_COMPLETE      # 짧은 상승도 에러 없이 완료
    assert Alarm.UP_TIMEOUT not in ctrl.alarms
    assert not ctrl.alarms
    assert ctrl.count == 1


def test_auto_complete_moves_to_exchange_position():
    """자동 반복 완료 → 교체 위치(상승 센서)로 이동 후 AUTO_COMPLETE 정지."""
    ctrl, a1, a2, ai, clk = _build(down_timeout_ms=100, up_timeout_ms=100,
                                   down_dwell_ms=20, up_dwell_ms=20, target_count=1,
                                   exchange_up_timeout_ms=5000)
    _di(a1, DI1.SOL_ENABLE_OK, True)
    _di(a1, DI1.MODE_AUTO, True)
    ctrl.scan()
    _di(a1, DI1.AUTO_START_PB, True); ctrl.scan(); _di(a1, DI1.AUTO_START_PB, False)
    saw_exchange = drove_up = False
    for _ in range(300):
        clk.advance(0.03); ctrl.scan()
        _di(a1, DI1.CYL_DOWN_POS, bool(ctrl.out.valve_down))   # 하강만 즉시 도달
        if ctrl.state is State.AUTO_EXCHANGE_UP:
            saw_exchange = True
            if ctrl.out.valve_up:                   # 교체 이동 = 상승 구동
                drove_up = True
                _di(a1, DI1.CYL_UP_POS, True)       # 상승 센서 도달 시뮬
        if ctrl.state is State.AUTO_COMPLETE:
            break
    assert saw_exchange and drove_up                # 완료 후 교체 위치로 상승 이동함
    assert ctrl.state is State.AUTO_COMPLETE
    assert ctrl.count == 1
    assert not ctrl.out.valve_up and not ctrl.out.valve_down   # 그 자리 정지
    assert not ctrl.alarms


def test_auto_stop_aborts():
    ctrl, a1, a2, ai, clk = _build()
    _di(a1, DI1.SOL_ENABLE_OK, True)
    _di(a1, DI1.MODE_AUTO, True)
    ctrl.scan()
    _di(a1, DI1.AUTO_START_PB, True); ctrl.scan(); _di(a1, DI1.AUTO_START_PB, False)
    clk.advance(0.03); ctrl.scan()
    assert ctrl.state.name.startswith("AUTO_")
    _di(a1, DI1.AUTO_STOP_PB, True)
    clk.advance(0.03); ctrl.scan()
    assert ctrl.state is State.AUTO_IDLE
    assert not ctrl.out.valve_down and not ctrl.out.valve_up


def test_load_over_limit():
    ctrl, a1, a2, ai, clk = _build(load_limit_kgf=100.0)
    _di(a1, DI1.SOL_ENABLE_OK, True)
    _di(a1, DI1.MODE_AUTO, True)
    ctrl.scan()
    _di(a1, DI1.AUTO_START_PB, True); ctrl.scan(); _di(a1, DI1.AUTO_START_PB, False)
    ai.set_mock_load_kgf(0, 500.0, ctrl.cfg.loadcell_full_scale_kgf)
    for _ in range(20):
        clk.advance(0.03); ctrl.scan()
        if ctrl.state is State.ERROR:
            break
    assert ctrl.state is State.ERROR
    assert Alarm.LOAD_OVER_LIMIT in ctrl.alarms


def test_cycle_peak_resets_run_peak_persists():
    ctrl, a1, a2, ai, clk = _build(target_count=2, down_dwell_ms=60, up_dwell_ms=60,
                                   down_timeout_ms=3000, up_timeout_ms=3000)
    _di(a1, DI1.SOL_ENABLE_OK, True)
    _di(a1, DI1.MODE_AUTO, True)
    ctrl.scan()
    _di(a1, DI1.AUTO_START_PB, True); ctrl.scan(); _di(a1, DI1.AUTO_START_PB, False)
    hi = False
    for _ in range(500):                       # 사이클1: 하중 300 주입
        clk.advance(0.02); ctrl.scan(); _plant(ctrl, a1)
        if ctrl.state is State.AUTO_DWELL_DOWN and not hi:
            ai.set_mock_load_kgf(0, 300.0, ctrl.cfg.loadcell_full_scale_kgf); hi = True
        if ctrl.count >= 1:
            break
    assert ctrl.run_peak_load_kgf >= 299
    ai.set_mock_load_kgf(0, 20.0, ctrl.cfg.loadcell_full_scale_kgf)  # 사이클2: 낮은 하중
    for _ in range(500):
        clk.advance(0.02); ctrl.scan(); _plant(ctrl, a1)
        if ctrl.state in (State.AUTO_COMPLETE, State.ERROR):
            break
    assert ctrl.state is State.AUTO_COMPLETE
    assert ctrl.run_peak_load_kgf >= 299       # 운전 최대 유지
    assert ctrl.cycle_peak_load_kgf < 100      # 사이클 최대는 리셋됨


# ---------------------------------------------------------------- vacuum (완전 분리)
def test_manual_vacuum_grab_and_warn_nonblocking():
    ctrl, a1, a2, ai, clk = _build(vacuum_confirm_timeout_ms=200)
    _di(a1, DI1.SOL_ENABLE_OK, True)
    _di(a1, DI1.MODE_AUTO, False)
    ctrl.scan()
    ctrl.set_vacuum(True)
    ctrl.scan()
    assert ctrl.out.vacuum_on is True
    assert a2.read_do()[int(DO2.K_VACUUM_ON)] is True
    for _ in range(20):
        clk.advance(0.03); ctrl.scan()
        if Alarm.VACUUM_NOT_REACHED in ctrl.vacuum_warnings:
            break
    assert Alarm.VACUUM_NOT_REACHED in ctrl.vacuum_warnings
    assert not ctrl.alarms                     # 논블로킹 — 블로킹 알람 없음
    assert ctrl.state is not State.ERROR
    _di(a2, DI2.VACUUM_OK, True)
    ctrl.scan()
    assert Alarm.VACUUM_NOT_REACHED not in ctrl.vacuum_warnings


def test_vacuum_warning_does_not_block_auto():
    ctrl, a1, a2, ai, clk = _build(vacuum_confirm_timeout_ms=100)
    _di(a1, DI1.SOL_ENABLE_OK, True)
    _di(a1, DI1.MODE_AUTO, True)
    ctrl.scan()
    ctrl.set_vacuum(True)                       # VACUUM_OK 없이 진공 ON
    for _ in range(8):
        clk.advance(0.03); ctrl.scan()
    assert Alarm.VACUUM_NOT_REACHED in ctrl.vacuum_warnings
    _di(a1, DI1.AUTO_START_PB, True); ctrl.scan(); _di(a1, DI1.AUTO_START_PB, False)
    clk.advance(0.03); ctrl.scan()
    assert ctrl.state.name.startswith("AUTO_") and ctrl.state is not State.AUTO_IDLE
    assert ctrl.out.vacuum_on is True          # 자동 중에도 진공 유지 (독립)


def test_vacuum_off_no_auto_blowoff():
    ctrl, a1, a2, ai, clk = _build()
    _di(a1, DI1.SOL_ENABLE_OK, True)
    _di(a1, DI1.MODE_AUTO, False)
    ctrl.scan()
    ctrl.set_vacuum(True); ctrl.scan()
    _di(a2, DI2.VACUUM_OK, True); ctrl.scan()
    ctrl.set_vacuum(False); ctrl.scan()
    assert ctrl.out.vacuum_on is False
    assert ctrl.out.blow_off_on is False       # 자동 blow-off 없음
    clk.advance(0.3); ctrl.scan()
    assert ctrl.out.blow_off_on is False


def test_vacuum_on_rejected_when_sol_off():
    ctrl, a1, a2, ai, clk = _build()
    _di(a1, DI1.SOL_ENABLE_OK, False)
    _di(a1, DI1.MODE_AUTO, False)
    ctrl.scan()                                # SAFETY_STOP
    ctrl.set_vacuum(True)                       # 허용조건 불만족 → 래치 안 됨
    ctrl.scan()
    assert ctrl.vacuum_command is False
    assert ctrl.out.vacuum_on is False


def test_vacuum_sensor_ignored_when_not_commanded():
    """진공 미명령 시 센서가 ON 이어도 시스템은 완전히 무시 — 이상경고 없음, 상태 OFF.

    (진공은 수동 전용이며 시스템 동작과 무관해야 한다. 센서가 NPN 등으로 반대로 읽혀도
    자동 운전에 끼어들거나 화면에 '진공 잔압/이상'을 띄우지 않는다.)
    """
    ctrl, a1, a2, ai, clk = _build(vacuum_residual_ms=150)
    _di(a1, DI1.SOL_ENABLE_OK, True)
    _di(a1, DI1.MODE_AUTO, False)
    ctrl.scan()
    _di(a2, DI2.VACUUM_OK, True)                # 명령 OFF 인데 센서 ON 지속
    for _ in range(20):
        clk.advance(0.03); ctrl.scan()
    assert Alarm.VACUUM_SIGNAL_ABNORMAL not in ctrl.vacuum_warnings
    assert not ctrl.alarms
    assert ctrl.vacuum_status() == "OFF"       # 센서 무시하고 OFF
    assert ctrl.out.vacuum_on is False


def test_maintenance_blowoff_hold():
    ctrl, a1, a2, ai, clk = _build(blowoff_delay_ms=80, blowoff_hold_ms=200)
    _di(a1, DI1.SOL_ENABLE_OK, True)
    _di(a1, DI1.MODE_AUTO, False)
    ctrl.scan()                                # MANUAL_IDLE
    ctrl.request_maintenance_blowoff(True)
    ctrl.scan()
    assert ctrl.out.blow_off_on is False       # delay 중
    clk.advance(0.1); ctrl.scan()
    assert ctrl.out.blow_off_on is True        # delay 후 hold
    ctrl.request_maintenance_blowoff(False)
    ctrl.scan()
    assert ctrl.out.blow_off_on is False       # 해제 → OFF


def test_do_override_lamp_only():
    ctrl, a1, a2, ai, clk = _build()
    _di(a1, DI1.SOL_ENABLE_OK, True)
    _di(a1, DI1.MODE_AUTO, False)
    ctrl.scan()                                # MANUAL_IDLE
    ctrl.set_do_override(DO1.LAMP_AUTO_START, True)
    ctrl.set_do_override(DO1.K_VALVE_DOWN, True)  # 액추에이터 → 무시돼야 함
    ctrl.scan()
    assert a1.read_do()[int(DO1.LAMP_AUTO_START)] is True
    assert a1.read_do()[int(DO1.K_VALVE_DOWN)] is False
    ctrl.clear_do_overrides()
    assert ctrl._do_override == {}


def test_do_override_ignored_when_auto_running():
    ctrl, a1, a2, ai, clk = _build()
    _di(a1, DI1.SOL_ENABLE_OK, True)
    _di(a1, DI1.MODE_AUTO, True)
    ctrl.scan()
    _di(a1, DI1.AUTO_START_PB, True); ctrl.scan(); _di(a1, DI1.AUTO_START_PB, False)
    clk.advance(0.03); ctrl.scan()             # 자동 진행 중
    assert ctrl._auto_running()
    ctrl.set_do_override(DO1.LAMP_AUTO_START, True)
    clk.advance(0.03); ctrl.scan()
    # 자동운전 중에는 오버라이드가 출력에 반영되지 않는다(컨트롤러 타워 로직이 유지).
    # 저장(튜플 키)은 되지만 _stage_and_flush 에서 auto_running 게이트로 미적용.
    assert ("DO1", int(DO1.LAMP_AUTO_START)) in ctrl._do_override


# ---------------------------------------------------------------- 교체 위치 (F2)
def test_exchange_position_moves_up_to_sensor():
    ctrl, a1, a2, ai, clk = _build(up_timeout_ms=1000)
    _di(a1, DI1.SOL_ENABLE_OK, True)
    _di(a1, DI1.MODE_AUTO, False)
    ctrl.scan()                                # MANUAL_IDLE
    ctrl.cmd_exchange_position()
    ctrl.scan()
    assert ctrl.state is State.MANUAL_MOVE_UP
    clk.advance(0.03); ctrl.scan()
    assert ctrl.out.valve_up is True           # 상승 센서 전까지 상승
    _di(a1, DI1.CYL_UP_POS, True)              # 상승 센서 도달
    clk.advance(0.03); ctrl.scan()
    assert ctrl.state is State.MANUAL_IDLE
    assert ctrl.out.valve_up is False


def test_exchange_position_timeout():
    # 교체 이동은 exchange_up_timeout_ms 를 쓴다(짧은 up_timeout_ms 와 분리).
    ctrl, a1, a2, ai, clk = _build(exchange_up_timeout_ms=100)
    _di(a1, DI1.SOL_ENABLE_OK, True)
    _di(a1, DI1.MODE_AUTO, False)
    ctrl.scan()
    ctrl.cmd_exchange_position(); ctrl.scan()
    for _ in range(20):
        clk.advance(0.03); ctrl.scan()
        if ctrl.state is State.ERROR:
            break
    assert ctrl.state is State.ERROR
    assert Alarm.UP_TIMEOUT in ctrl.alarms


def test_exchange_ignored_in_auto():
    ctrl, a1, a2, ai, clk = _build()
    _di(a1, DI1.SOL_ENABLE_OK, True)
    _di(a1, DI1.MODE_AUTO, True)
    ctrl.scan()                                # AUTO_IDLE
    ctrl.cmd_exchange_position()
    ctrl.scan()
    assert ctrl.state is State.AUTO_IDLE       # 자동에서는 무시


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  PASS  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} passed")


if __name__ == "__main__":
    _run_all()
