"""Phase B 상태머신 테스트 (mock 하드웨어 + 주입 clock + 가상 실린더 플랜트).

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


def _build(**cfg_over):
    cfg = replace(
        Config(),
        target_count=cfg_over.pop("target_count", 2),
        move_timeout_ms=cfg_over.pop("move_timeout_ms", 1000),
        down_dwell_ms=cfg_over.pop("down_dwell_ms", 100),
        up_dwell_ms=cfg_over.pop("up_dwell_ms", 100),
        vacuum_timeout_ms=cfg_over.pop("vacuum_timeout_ms", 500),
        blowoff_delay_ms=cfg_over.pop("blowoff_delay_ms", 80),
        blowoff_hold_ms=cfg_over.pop("blowoff_hold_ms", 150),
        **cfg_over,
    )
    a1 = Adam4055(None, 1, mock=True)
    a2 = Adam4055(None, 2, mock=True)
    ai = Adam4017(None, 3, mock=True)
    ai.set_mock_ma(0, 4.0)                 # 0 kgf 기본
    io = IO(a1, a2, ai)
    tmp = os.path.join(tempfile.gettempdir(), "cal_ctrl.json")
    if os.path.exists(tmp):
        os.remove(tmp)
    lc = LoadCell(ai, 0, cfg.loadcell_full_scale_kgf, tmp)
    clk = Clock()
    ctrl = Controller(cfg, io, lc, clock=clk)
    return ctrl, a1, a2, ai, clk


def _di(module, sig, val):
    module.set_mock_di(int(sig), val)


# ---------------------------------------------------------------- safety unit
def test_safety_sol_disable_kills_actuators():
    o = Outputs(valve_down=True, vacuum_on=True)
    apply_output_safety(o, sol_enable_ok=False)
    assert not o.valve_down and not o.vacuum_on


def test_safety_valve_interlock():
    o = Outputs(valve_down=True, valve_up=True)
    alarms = apply_output_safety(o, sol_enable_ok=True)
    assert not o.valve_down and not o.valve_up
    assert Alarm.VALVE_INTERLOCK in alarms


def test_safety_vacuum_blowoff_interlock():
    o = Outputs(vacuum_on=True, blow_off_on=True)
    alarms = apply_output_safety(o, sol_enable_ok=True)
    assert not o.vacuum_on and not o.blow_off_on
    assert Alarm.VACUUM_BLOWOFF_INTERLOCK in alarms


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
    assert ctrl.state is State.AUTO_IDLE

    _di(a1, DI1.SOL_ENABLE_OK, False)      # EMO/Area 차단
    ctrl.scan()
    assert ctrl.state is State.SAFETY_STOP

    _di(a1, DI1.SOL_ENABLE_OK, True)       # 복귀만으로는 해제 안 됨
    ctrl.scan()
    assert ctrl.state is State.SAFETY_STOP

    ctrl.cmd_safety_reset()                # HMI Safety Reset 필요
    ctrl.scan()
    assert ctrl.state is State.AUTO_IDLE


# ---------------------------------------------------------------- manual
def test_manual_up_down_and_conflict():
    ctrl, a1, a2, ai, clk = _build()
    _di(a1, DI1.SOL_ENABLE_OK, True)
    _di(a1, DI1.MODE_AUTO, False)
    ctrl.scan()
    assert ctrl.state is State.MANUAL_IDLE

    _di(a1, DI1.MANUAL_UP_PB, True)
    ctrl.scan()
    assert ctrl.out.valve_up and not ctrl.out.valve_down
    assert a1.read_do()[int(DO1.K_VALVE_UP)] is True

    _di(a1, DI1.MANUAL_UP_PB, False)
    _di(a1, DI1.MANUAL_DOWN_PB, True)
    ctrl.scan()
    assert ctrl.out.valve_down and not ctrl.out.valve_up

    _di(a1, DI1.MANUAL_UP_PB, True)        # 동시 → conflict
    ctrl.scan()
    assert not ctrl.out.valve_up and not ctrl.out.valve_down
    assert Alarm.MANUAL_CONFLICT in ctrl.alarms


def test_manual_blocked_when_sol_off():
    ctrl, a1, a2, ai, clk = _build()
    _di(a1, DI1.SOL_ENABLE_OK, False)
    _di(a1, DI1.MODE_AUTO, False)
    ctrl.scan()                            # SOL off → SAFETY_STOP
    _di(a1, DI1.MANUAL_UP_PB, True)
    ctrl.scan()
    assert not ctrl.out.valve_up           # 안전 차단


# ---------------------------------------------------------------- auto cycle
def _plant_react(ctrl, a1):
    """가상 실린더: 밸브 지령에 따라 위치 센서를 즉시 반영."""
    if ctrl.out.valve_down:
        _di(a1, DI1.CYL_DOWN_POS, True)
        _di(a1, DI1.CYL_UP_POS, False)
    elif ctrl.out.valve_up:
        _di(a1, DI1.CYL_UP_POS, True)
        _di(a1, DI1.CYL_DOWN_POS, False)


def test_auto_full_cycle_reaches_complete():
    ctrl, a1, a2, ai, clk = _build(target_count=2)
    _di(a1, DI1.SOL_ENABLE_OK, True)
    _di(a1, DI1.MODE_AUTO, True)
    ctrl.scan()
    assert ctrl.state is State.AUTO_IDLE

    _di(a1, DI1.AUTO_START_PB, True)       # 시작 (rising)
    ctrl.scan()
    _di(a1, DI1.AUTO_START_PB, False)

    seen_down = seen_up = False
    for _ in range(400):
        clk.advance(0.03)
        ctrl.scan()
        _plant_react(ctrl, a1)
        if ctrl.out.valve_down:
            seen_down = True
        if ctrl.out.valve_up:
            seen_up = True
        if ctrl.state in (State.AUTO_COMPLETE, State.ERROR):
            break

    assert ctrl.state is State.AUTO_COMPLETE, ctrl.state
    assert ctrl.count == 2, ctrl.count
    assert seen_down and seen_up            # 실제로 하강/상승 지령이 났다
    assert not ctrl.alarms


def test_auto_down_timeout():
    ctrl, a1, a2, ai, clk = _build(move_timeout_ms=200)
    _di(a1, DI1.SOL_ENABLE_OK, True)
    _di(a1, DI1.MODE_AUTO, True)
    ctrl.scan()
    _di(a1, DI1.AUTO_START_PB, True)
    ctrl.scan()
    _di(a1, DI1.AUTO_START_PB, False)
    # CYL_DOWN_POS 를 절대 안 주고 시간만 흘린다 → DOWN_TIMEOUT
    for _ in range(50):
        clk.advance(0.03)
        ctrl.scan()
        if ctrl.state is State.ERROR:
            break
    assert ctrl.state is State.ERROR
    assert Alarm.DOWN_TIMEOUT in ctrl.alarms
    # Alarm Clear 로 복귀
    ctrl.cmd_alarm_clear()
    ctrl.scan()
    assert ctrl.state is State.AUTO_IDLE
    assert not ctrl.alarms


def test_auto_stop_aborts():
    ctrl, a1, a2, ai, clk = _build()
    _di(a1, DI1.SOL_ENABLE_OK, True)
    _di(a1, DI1.MODE_AUTO, True)
    ctrl.scan()
    _di(a1, DI1.AUTO_START_PB, True)
    ctrl.scan()
    _di(a1, DI1.AUTO_START_PB, False)
    clk.advance(0.03); ctrl.scan()         # PRECHECK→MOVE_DOWN 진입
    assert ctrl.state.name.startswith("AUTO_")
    _di(a1, DI1.AUTO_STOP_PB, True)        # 정지 (rising)
    clk.advance(0.03); ctrl.scan()
    assert ctrl.state is State.AUTO_IDLE
    assert not ctrl.out.valve_down and not ctrl.out.valve_up


# ---------------------------------------------------------------- load limit
def test_load_over_limit():
    ctrl, a1, a2, ai, clk = _build(load_limit_kgf=100.0)
    _di(a1, DI1.SOL_ENABLE_OK, True)
    _di(a1, DI1.MODE_AUTO, True)
    ctrl.scan()
    _di(a1, DI1.AUTO_START_PB, True)
    ctrl.scan()
    _di(a1, DI1.AUTO_START_PB, False)
    ai.set_mock_load_kgf(0, 500.0, ctrl.cfg.loadcell_full_scale_kgf)  # 과하중
    for _ in range(20):
        clk.advance(0.03)
        ctrl.scan()
        if ctrl.state is State.ERROR:
            break
    assert ctrl.state is State.ERROR
    assert Alarm.LOAD_OVER_LIMIT in ctrl.alarms


# ---------------------------------------------------------------- vacuum (manual)
def test_manual_vacuum_grab_and_fail():
    ctrl, a1, a2, ai, clk = _build(vacuum_timeout_ms=200)
    _di(a1, DI1.SOL_ENABLE_OK, True)
    _di(a1, DI1.MODE_AUTO, False)
    ctrl.scan()
    ctrl.set_vacuum(True)
    ctrl.scan()
    assert ctrl.out.vacuum_on is True
    assert a2.read_do()[int(DO2.K_VACUUM_ON)] is True

    # VACUUM_OK 안 주고 timeout → VACUUM_FAIL
    for _ in range(20):
        clk.advance(0.03)
        ctrl.scan()
        if Alarm.VACUUM_FAIL in ctrl.alarms:
            break
    assert Alarm.VACUUM_FAIL in ctrl.alarms

    # VACUUM_OK 도달 → 알람 해제
    _di(a2, DI2.VACUUM_OK, True)
    ctrl.scan()
    assert Alarm.VACUUM_FAIL not in ctrl.alarms


def test_manual_vacuum_release_blowoff_pulse():
    ctrl, a1, a2, ai, clk = _build(blowoff_delay_ms=80, blowoff_hold_ms=150)
    _di(a1, DI1.SOL_ENABLE_OK, True)
    _di(a1, DI1.MODE_AUTO, False)
    ctrl.scan()
    ctrl.set_vacuum(True)
    ctrl.scan()
    _di(a2, DI2.VACUUM_OK, True)
    ctrl.scan()

    ctrl.set_vacuum(False)                 # 해제 → blow-off 펄스 시작
    ctrl.scan()
    assert ctrl.out.vacuum_on is False

    # delay(80ms) 경과 후 blow_off ON
    clk.advance(0.1); ctrl.scan()
    assert ctrl.out.blow_off_on is True
    # hold(150ms) 경과 후 blow_off OFF
    clk.advance(0.2); ctrl.scan()
    assert ctrl.out.blow_off_on is False


def test_vacuum_gated_by_sol():
    ctrl, a1, a2, ai, clk = _build()
    _di(a1, DI1.SOL_ENABLE_OK, False)
    _di(a1, DI1.MODE_AUTO, False)
    ctrl.scan()                            # SAFETY_STOP
    ctrl.set_vacuum(True)
    ctrl.scan()
    assert ctrl.out.vacuum_on is False     # SOL off → 진공 차단


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  PASS  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} passed")


if __name__ == "__main__":
    _run_all()
