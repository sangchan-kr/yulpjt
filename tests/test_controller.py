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


def test_auto_down_timeout():
    ctrl, a1, a2, ai, clk = _build(down_timeout_ms=200)
    _di(a1, DI1.SOL_ENABLE_OK, True)
    _di(a1, DI1.MODE_AUTO, True)
    ctrl.scan()
    _di(a1, DI1.AUTO_START_PB, True); ctrl.scan(); _di(a1, DI1.AUTO_START_PB, False)
    for _ in range(50):
        clk.advance(0.03); ctrl.scan()
        if ctrl.state is State.ERROR:
            break
    assert ctrl.state is State.ERROR
    assert Alarm.DOWN_TIMEOUT in ctrl.alarms
    ctrl.cmd_alarm_clear()
    ctrl.scan()
    assert ctrl.state is State.AUTO_IDLE
    assert not ctrl.alarms


def test_separate_up_timeout():
    # 하강은 즉시 도달, 상승만 미도달 → UP_TIMEOUT (timeout 분리 확인)
    ctrl, a1, a2, ai, clk = _build(down_timeout_ms=2000, up_timeout_ms=150, down_dwell_ms=20)
    _di(a1, DI1.SOL_ENABLE_OK, True)
    _di(a1, DI1.MODE_AUTO, True)
    ctrl.scan()
    _di(a1, DI1.AUTO_START_PB, True); ctrl.scan(); _di(a1, DI1.AUTO_START_PB, False)
    for _ in range(200):
        clk.advance(0.03); ctrl.scan()
        if ctrl.out.valve_down:                # 하강 지령 → 즉시 도달만 시뮬
            _di(a1, DI1.CYL_DOWN_POS, True)
        # 상승 위치는 절대 주지 않음
        if ctrl.state is State.ERROR:
            break
    assert Alarm.UP_TIMEOUT in ctrl.alarms


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


def test_vacuum_signal_abnormal_warning():
    ctrl, a1, a2, ai, clk = _build(vacuum_residual_ms=150)
    _di(a1, DI1.SOL_ENABLE_OK, True)
    _di(a1, DI1.MODE_AUTO, False)
    ctrl.scan()
    _di(a2, DI2.VACUUM_OK, True)                # 명령 OFF 인데 OK 지속
    for _ in range(20):
        clk.advance(0.03); ctrl.scan()
        if Alarm.VACUUM_SIGNAL_ABNORMAL in ctrl.vacuum_warnings:
            break
    assert Alarm.VACUUM_SIGNAL_ABNORMAL in ctrl.vacuum_warnings
    assert not ctrl.alarms                     # 논블로킹


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


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  PASS  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} passed")


if __name__ == "__main__":
    _run_all()
