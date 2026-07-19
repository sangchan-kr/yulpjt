"""제어 상태머신 (v1.12 + HMI handoff v0.2).

한 스캔(scan)마다:
  입력 읽기 → 전역 처리(안전 래치/모드/HMI명령) → 상태 로직 → 진공(완전 분리) →
  타워 표시 → 출력 안전 초크포인트 → 실제 출력 flush.

진공 설계 원칙(완전 분리):
  - 진공은 자동 시퀀스에 없다. 작업자 수동 명령(vacuum_command)으로만 구동.
  - 진공 알람은 모두 논블로킹 경고(vacuum_warnings) — 자동운전/기계 상태/타워에
    영향을 주지 않는다.
  - Vacuum OFF 는 K_VACUUM_ON 만 끈다. 자동 blow-off 는 없다(유지보수 전용).
  - Safety Stop / 통신오류 시 진공 명령을 래치 OFF 하고 자동 복원하지 않는다.

시간은 주입 가능한 clock() 으로 다뤄 테스트에서 결정적으로 굴린다.
"""

import time

from ..config import Config
from ..hardware.signals import AI, DI1, DI2, DO1, DO2, IO
from .safety import apply_output_safety
from .states import Alarm, Outputs, State


class Controller:
    def __init__(self, cfg: Config, io: IO, loadcell, *, clock=time.monotonic) -> None:
        self.cfg = cfg
        self.io = io
        self.loadcell = loadcell
        self._clock = clock

        self.state = State.BOOT
        self.alarms: set[Alarm] = set()            # 블로킹 알람만
        self.vacuum_warnings: set[Alarm] = set()   # 논블로킹 진공 경고 (완전 분리)
        self.out = Outputs()

        # 카운트/하중
        self.count = 0
        self.target_count = cfg.target_count
        self.load_kgf = 0.0
        self.cycle_peak_load_kgf = 0.0             # 현재 사이클 최대
        self.run_peak_load_kgf = 0.0               # 전체 운전 최대

        # 입력 캐시
        self.sol_enable_ok = False
        self.mode_auto = False
        self.vacuum_ok = False
        self.adam2_connected = True                # 실통신 게이팅은 Phase D
        self._prev_di: dict = {}

        # 타이머
        self._t_deadline: float | None = None
        self._t_dwell_end: float | None = None
        self._t_vac_deadline: float | None = None
        self._t_residual: float | None = None
        self._t_blowoff: float | None = None
        self._blowoff_phase = 0

        # 진공 (수동, 자동과 분리)
        self.vacuum_command = False
        self.vacuum_reason: str | None = None
        self._prev_vacuum_on = False
        self._maint_blowoff_req = False            # 유지보수 hold-to-run
        self._prev_maint_req = False

        # HMI 명령 플래그
        self._cmd_safety_reset = False
        self._cmd_alarm_clear = False
        self._cmd_count_reset = False
        self._cmd_load_zero = False

        self._now = self._clock()

    # ================================================================= 명령 (HMI)
    def cmd_safety_reset(self) -> None:
        self._cmd_safety_reset = True

    def cmd_alarm_clear(self) -> None:
        self._cmd_alarm_clear = True

    def cmd_count_reset(self) -> None:
        self._cmd_count_reset = True

    def cmd_load_zero(self) -> None:
        self._cmd_load_zero = True

    def set_vacuum(self, on: bool) -> None:
        """수동 진공 토글. ON 은 허용조건을 만족할 때만 래치된다."""
        if on:
            allowed, _ = self.vacuum_permission()
            if allowed:
                self.vacuum_command = True
        else:
            self.vacuum_command = False

    def request_maintenance_blowoff(self, on: bool) -> None:
        """유지보수 화면 전용 blow-off hold-to-run 요청."""
        self._maint_blowoff_req = bool(on)

    def vacuum_permission(self):
        """(allowed, reason). 진공 ON 허용조건 (HMI handoff §6.1)."""
        if self.state is State.SAFETY_STOP:
            return False, "SAFETY_STOP"
        if not self.sol_enable_ok:
            return False, "SOL_ENABLE_OFF"
        if not self.adam2_connected:
            return False, "ADAM2_DISCONNECTED"
        if Alarm.ADAM_COMM_ERROR in self.alarms:
            return False, "ADAM_COMM_ERROR"
        if self._maint_blowoff_req:
            return False, "BLOWOFF_ACTIVE"
        return True, None

    # ================================================================= 스캔
    def scan(self) -> None:
        self._now = self._clock()
        self.io.refresh_inputs()
        self._read_inputs()
        self._handle_global()
        self._run_state()
        self._update_vacuum()
        self._update_tower()

        # §19 단일 출력 초크포인트 (진공 경고는 절대 블로킹 목록에 넣지 않는다)
        blocking, warnings = apply_output_safety(self.out, self.sol_enable_ok, self.adam2_connected)
        self.alarms.update(blocking)
        self.vacuum_warnings.update(warnings)

        self._stage_and_flush()

    # ----------------------------------------------------------------- 입력
    def _read_inputs(self) -> None:
        self.sol_enable_ok = self.io.di(DI1.SOL_ENABLE_OK)
        self.mode_auto = self.io.di(DI1.MODE_AUTO)
        self.vacuum_ok = self.io.di(DI2.VACUUM_OK)

        self.load_kgf = self.loadcell.read_kgf()
        if self.load_kgf > self.run_peak_load_kgf:
            self.run_peak_load_kgf = self.load_kgf
        if self.load_kgf > self.cycle_peak_load_kgf:
            self.cycle_peak_load_kgf = self.load_kgf

    def _rising(self, sig) -> bool:
        return self.io.di(sig) and not self._prev_di.get(sig, False)

    def _latch_prev(self) -> None:
        for sig in (DI1.AUTO_START_PB, DI1.AUTO_STOP_PB, DI1.MANUAL_UP_PB, DI1.MANUAL_DOWN_PB):
            self._prev_di[sig] = self.io.di(sig)

    # ----------------------------------------------------------------- 전역
    def _handle_global(self) -> None:
        if self._cmd_load_zero:
            self.loadcell.tare()
            self._cmd_load_zero = False

        # SOL_ENABLE OFF → SAFETY_STOP 래치 + 진공 명령 래치 OFF(자동복원 금지)
        if not self.sol_enable_ok and self.state is not State.SAFETY_STOP:
            self.state = State.SAFETY_STOP
        if self.state is State.SAFETY_STOP:
            self.vacuum_command = False
            if self._cmd_safety_reset and self.sol_enable_ok:
                self.state = State.AUTO_IDLE if self.mode_auto else State.MANUAL_IDLE
            self._cmd_safety_reset = False

        # 통신 오류 시에도 진공 명령 래치 OFF (자동복원 금지)
        if Alarm.ADAM_COMM_ERROR in self.alarms:
            self.vacuum_command = False

        # ERROR 는 원인 제거 후 Alarm Clear 로 복귀 (블로킹 알람만 대상)
        if self.state is State.ERROR and self._cmd_alarm_clear:
            self.alarms.clear()
            self.state = State.AUTO_IDLE if self.mode_auto else State.MANUAL_IDLE
        self._cmd_alarm_clear = False

        if self._cmd_count_reset and self.state in (
            State.AUTO_IDLE, State.MANUAL_IDLE, State.AUTO_COMPLETE
        ):
            self.count = 0
            self.run_peak_load_kgf = 0.0
            self.cycle_peak_load_kgf = 0.0
        self._cmd_count_reset = False

        if self.state is State.AUTO_IDLE and not self.mode_auto:
            self.state = State.MANUAL_IDLE
        elif self.state is State.MANUAL_IDLE and self.mode_auto:
            self.state = State.AUTO_IDLE
        elif self.state is State.BOOT:
            self.state = State.AUTO_IDLE if self.mode_auto else State.MANUAL_IDLE

    # ----------------------------------------------------------------- 상태 로직
    def _run_state(self) -> None:
        self.out.valve_down = False
        self.out.valve_up = False

        s = self.state
        if s in (State.SAFETY_STOP, State.ERROR, State.BOOT):
            pass
        elif s is State.MANUAL_IDLE:
            self._run_manual()
        elif s is State.AUTO_IDLE:
            if self._rising(DI1.AUTO_START_PB):
                self.state = State.AUTO_PRECHECK
        elif s is State.AUTO_PRECHECK:
            self._run_precheck()
        elif s is State.AUTO_MOVE_DOWN:
            self._run_move_down()
        elif s is State.AUTO_DWELL_DOWN:
            self._run_dwell_down()
        elif s is State.AUTO_MOVE_UP:
            self._run_move_up()
        elif s is State.AUTO_DWELL_UP:
            self._run_dwell_up()
        elif s is State.AUTO_COUNT_UPDATE:
            self._run_count_update()

        if s.name.startswith("AUTO_") and s not in (State.AUTO_IDLE, State.AUTO_COMPLETE):
            if self._rising(DI1.AUTO_STOP_PB):
                self._abort_auto(State.AUTO_IDLE)

        self._latch_prev()

    def _run_manual(self) -> None:
        up = self.io.di(DI1.MANUAL_UP_PB)
        down = self.io.di(DI1.MANUAL_DOWN_PB)
        if up and down:
            self.alarms.add(Alarm.MANUAL_CONFLICT)
            self.out.valve_up = False
            self.out.valve_down = False
        else:
            self.alarms.discard(Alarm.MANUAL_CONFLICT)
            self.out.valve_up = up
            self.out.valve_down = down

    def _run_precheck(self) -> None:
        # 진공은 Auto Start 허가 조건이 아니다(완전 분리). 블로킹 알람만 확인.
        if self.alarms or not self.mode_auto or not self.sol_enable_ok:
            self._abort_auto(State.AUTO_IDLE)
            return
        self._start_move(State.AUTO_MOVE_DOWN, self.cfg.down_timeout_ms)

    def _run_move_down(self) -> None:
        self.out.valve_down = True
        if self.load_kgf > self.cfg.load_limit_kgf:
            self._fault(Alarm.LOAD_OVER_LIMIT)
            return
        if self.io.di(DI1.CYL_DOWN_POS):
            self._start_dwell(State.AUTO_DWELL_DOWN, self.cfg.down_dwell_ms)
        elif self._deadline_passed():
            self._fault(Alarm.DOWN_TIMEOUT)

    def _run_dwell_down(self) -> None:
        if self.load_kgf > self.cfg.load_limit_kgf:
            self._fault(Alarm.LOAD_OVER_LIMIT)
            return
        if self._now >= self._t_dwell_end:
            self._start_move(State.AUTO_MOVE_UP, self.cfg.up_timeout_ms)

    def _run_move_up(self) -> None:
        self.out.valve_up = True
        if self.io.di(DI1.CYL_UP_POS):
            self._start_dwell(State.AUTO_DWELL_UP, self.cfg.up_dwell_ms)
        elif self._deadline_passed():
            self._fault(Alarm.UP_TIMEOUT)

    def _run_dwell_up(self) -> None:
        if self._now >= self._t_dwell_end:
            self.state = State.AUTO_COUNT_UPDATE

    def _run_count_update(self) -> None:
        self.count += 1
        if self.count >= self.target_count:
            self.state = State.AUTO_COMPLETE
        else:
            self._start_move(State.AUTO_MOVE_DOWN, self.cfg.down_timeout_ms)

    # ----------------------------------------------------------------- 진공 (수동, 분리)
    def _update_vacuum(self) -> None:
        allowed, reason = self.vacuum_permission()
        self.vacuum_reason = reason

        on = self.vacuum_command and allowed
        self.out.vacuum_on = on

        # 진공 도달 감시 (VACUUM_NOT_REACHED, 논블로킹 경고)
        if on:
            if not self._prev_vacuum_on:
                self._t_vac_deadline = self._now + self.cfg.vacuum_confirm_timeout_ms / 1000.0
            if self.vacuum_ok:
                self.vacuum_warnings.discard(Alarm.VACUUM_NOT_REACHED)
                self._t_vac_deadline = None
            elif self._t_vac_deadline is not None and self._now >= self._t_vac_deadline:
                self.vacuum_warnings.add(Alarm.VACUUM_NOT_REACHED)
        else:
            self.vacuum_warnings.discard(Alarm.VACUUM_NOT_REACHED)
            self._t_vac_deadline = None

        # 잔류/이상 신호 감시 (VACUUM_SIGNAL_ABNORMAL, 논블로킹 경고)
        if not self.vacuum_command and self.vacuum_ok:
            if self._t_residual is None:
                self._t_residual = self._now + self.cfg.vacuum_residual_ms / 1000.0
            elif self._now >= self._t_residual:
                self.vacuum_warnings.add(Alarm.VACUUM_SIGNAL_ABNORMAL)
        else:
            self._t_residual = None
            self.vacuum_warnings.discard(Alarm.VACUUM_SIGNAL_ABNORMAL)

        # 유지보수 blow-off (hold-to-run). 자동/메인에서는 절대 켜지지 않음.
        self._run_maint_blowoff()
        self._prev_vacuum_on = on

    def _run_maint_blowoff(self) -> None:
        ok = (
            self._maint_blowoff_req
            and self.sol_enable_ok
            and self.adam2_connected
            and not self.vacuum_command
            and not self._auto_running()
        )
        if ok and not self._prev_maint_req:
            self._blowoff_phase = 1
            self._t_blowoff = self._now + self.cfg.blowoff_delay_ms / 1000.0
        if not ok:
            self._blowoff_phase = 0
            self.out.blow_off_on = False
        else:
            if self._blowoff_phase == 1 and self._now >= self._t_blowoff:
                self._blowoff_phase = 2
                self._t_blowoff = self._now + self.cfg.blowoff_hold_ms / 1000.0
            self.out.blow_off_on = self._blowoff_phase == 2 and self._now < self._t_blowoff
        self._prev_maint_req = ok

    # ----------------------------------------------------------------- 타워
    def _update_tower(self) -> None:
        o = self.out
        o.tower_green = o.tower_yellow = o.tower_red = o.tower_buzzer = False
        blink = int(self._now * 2) % 2 == 0

        s = self.state
        if s is State.SAFETY_STOP:
            o.tower_red = blink
            o.tower_buzzer = blink
        elif s is State.ERROR or self.alarms:          # 블로킹 알람만 (진공 경고 무관)
            o.tower_red = True
            o.tower_buzzer = blink
        elif s in (State.AUTO_MOVE_DOWN, State.AUTO_DWELL_DOWN, State.AUTO_MOVE_UP,
                   State.AUTO_DWELL_UP, State.AUTO_COUNT_UPDATE, State.AUTO_PRECHECK):
            o.tower_green = blink
        elif s is State.AUTO_COMPLETE:
            o.tower_green = True
        elif s is State.MANUAL_IDLE:
            o.tower_yellow = blink
        else:
            o.tower_yellow = True

    # ----------------------------------------------------------------- 출력 반영
    def _stage_and_flush(self) -> None:
        o = self.out
        self.io.set(DO1.K_VALVE_DOWN, o.valve_down)
        self.io.set(DO1.K_VALVE_UP, o.valve_up)
        self.io.set(DO1.TOWER_GREEN, o.tower_green)
        self.io.set(DO1.TOWER_YELLOW, o.tower_yellow)
        self.io.set(DO1.TOWER_RED, o.tower_red)
        self.io.set(DO1.TOWER_BUZZER, o.tower_buzzer)
        self.io.set(DO2.K_VACUUM_ON, o.vacuum_on)
        self.io.set(DO2.K_BLOW_OFF_ON, o.blow_off_on)
        self.io.flush_outputs()

    # ----------------------------------------------------------------- 헬퍼
    def _auto_running(self) -> bool:
        return self.state.name.startswith("AUTO_") and self.state not in (
            State.AUTO_IDLE, State.AUTO_COMPLETE
        )

    def _start_move(self, state: State, timeout_ms: int) -> None:
        if state is State.AUTO_MOVE_DOWN:
            self.cycle_peak_load_kgf = 0.0          # 새 사이클 시작 → 사이클 최대 리셋
        self.state = state
        self._t_deadline = self._now + timeout_ms / 1000.0

    def _start_dwell(self, state: State, dwell_ms: int) -> None:
        self.state = state
        self._t_dwell_end = self._now + dwell_ms / 1000.0

    def _deadline_passed(self) -> bool:
        return self._t_deadline is not None and self._now >= self._t_deadline

    def _abort_auto(self, target: State) -> None:
        self.out.valve_down = False
        self.out.valve_up = False
        self.state = target

    def _fault(self, alarm: Alarm) -> None:
        self.alarms.add(alarm)
        self.out.valve_down = False
        self.out.valve_up = False
        self.state = State.ERROR
