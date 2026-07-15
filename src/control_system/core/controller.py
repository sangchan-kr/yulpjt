"""제어 상태머신 (v1.12 §8·11·12·14·19).

한 스캔(scan)마다:
  입력 읽기 → 전역 처리(안전 래치/모드/HMI 명령) → 상태 로직 → 수동 진공 →
  타워 표시 → 출력 안전 초크포인트 → 실제 출력 flush.

시간은 주입 가능한 clock() 으로 다뤄 테스트에서 결정적으로 굴릴 수 있다.
진공은 자동 시퀀스에서 빠지고 HMI 토글로만 제어한다(결정3).
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
        self.alarms: set[Alarm] = set()
        self.out = Outputs()

        # 카운트/하중
        self.count = 0
        self.target_count = cfg.target_count
        self.load_kgf = 0.0
        self.max_load_kgf = 0.0

        # 입력 캐시 / 엣지
        self.sol_enable_ok = False
        self.mode_auto = False
        self.vacuum_ok = False
        self._prev_di: dict = {}

        # 타이머 (목표 시각, None=미설정)
        self._t_deadline: float | None = None      # 이동 타임아웃
        self._t_dwell_end: float | None = None      # dwell 종료
        self._t_vac_deadline: float | None = None   # 진공 도달 타임아웃
        self._t_blowoff: float | None = None        # blow-off 단계 시각
        self._blowoff_phase = 0                      # 0=없음 1=delay 2=hold

        # HMI 명령 플래그 (UI 가 세팅, 다음 scan 에서 소비)
        self._cmd_safety_reset = False
        self._cmd_alarm_clear = False
        self._cmd_count_reset = False
        self._cmd_load_zero = False
        self._vacuum_cmd = False        # 수동 진공 토글 상태 (유지형)
        self._prev_vacuum_cmd = False

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
        """수동 진공 토글. on=True 흡착 유지, False 해제(blow-off 펄스)."""
        self._vacuum_cmd = bool(on)

    # ================================================================= 스캔
    def scan(self) -> None:
        self._now = self._clock()
        self.io.refresh_inputs()
        self._read_inputs()
        self._handle_global()
        self._run_state()
        self._update_vacuum()
        self._update_tower()

        # §19 단일 출력 초크포인트
        alarms = apply_output_safety(self.out, self.sol_enable_ok)
        for a in alarms:
            self.alarms.add(a)

        self._stage_and_flush()

    # ----------------------------------------------------------------- 입력
    def _read_inputs(self) -> None:
        self.sol_enable_ok = self.io.di(DI1.SOL_ENABLE_OK)
        self.mode_auto = self.io.di(DI1.MODE_AUTO)
        self.vacuum_ok = self.io.di(DI2.VACUUM_OK)

        # 하중
        self.load_kgf = self.loadcell.read_kgf()
        if self.load_kgf > self.max_load_kgf:
            self.max_load_kgf = self.load_kgf

    def _rising(self, sig) -> bool:
        cur = self.io.di(sig)
        prev = self._prev_di.get(sig, False)
        return cur and not prev

    def _latch_prev(self) -> None:
        for sig in (DI1.AUTO_START_PB, DI1.AUTO_STOP_PB, DI1.MANUAL_UP_PB, DI1.MANUAL_DOWN_PB):
            self._prev_di[sig] = self.io.di(sig)

    # ----------------------------------------------------------------- 전역
    def _handle_global(self) -> None:
        # HMI: 영점
        if self._cmd_load_zero:
            self.loadcell.tare()
            self._cmd_load_zero = False

        # SOL_ENABLE OFF → 즉시 SAFETY_STOP 래치 (§8.3)
        if not self.sol_enable_ok and self.state is not State.SAFETY_STOP:
            self.state = State.SAFETY_STOP

        # SAFETY_STOP: HMI Safety Reset + SOL_ENABLE 복귀로만 해제, 자동 재시작 없음
        if self.state is State.SAFETY_STOP:
            if self._cmd_safety_reset and self.sol_enable_ok:
                self.state = State.AUTO_IDLE if self.mode_auto else State.MANUAL_IDLE
            self._cmd_safety_reset = False

        # ERROR: 원인 제거 후 Alarm Clear 로 복귀
        if self.state is State.ERROR and self._cmd_alarm_clear:
            self.alarms.clear()
            self.state = State.AUTO_IDLE if self.mode_auto else State.MANUAL_IDLE
        self._cmd_alarm_clear = False

        # 일반 알람 클리어(상태 전환은 없이 원인 없는 알람 정리)는 위에서 소비됨.

        # 카운트 리셋 (Idle/Complete 에서만)
        if self._cmd_count_reset and self.state in (
            State.AUTO_IDLE, State.MANUAL_IDLE, State.AUTO_COMPLETE
        ):
            self.count = 0
            self.max_load_kgf = 0.0
        self._cmd_count_reset = False

        # 모드 스위치 (안전/에러가 아니고 idle 계열일 때만)
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
            pass  # 액추에이터 출력 없음
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
        elif s is State.AUTO_COMPLETE:
            pass

        # Auto 진행 중 Stop 버튼 → 중단하고 IDLE (§11.1)
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
        # 통신/알람/모드 확인. mock 에서는 통신 OK 가정.
        if self.alarms or not self.mode_auto or not self.sol_enable_ok:
            self._abort_auto(State.AUTO_IDLE)
            return
        self._start_move(State.AUTO_MOVE_DOWN)

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
        # 밸브 OFF = Closed Center 로 위치 유지, 하중 감시
        if self.load_kgf > self.cfg.load_limit_kgf:
            self._fault(Alarm.LOAD_OVER_LIMIT)
            return
        if self._now >= self._t_dwell_end:
            self._start_move(State.AUTO_MOVE_UP)

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
            self._start_move(State.AUTO_MOVE_DOWN)

    # ----------------------------------------------------------------- 진공(수동)
    def _update_vacuum(self) -> None:
        on = self._vacuum_cmd
        # 흡착 유지 중
        if on:
            self.out.vacuum_on = True
            self.out.blow_off_on = False
            if not self._prev_vacuum_cmd:            # 방금 켬 → 진공 도달 타임아웃 시작
                self._t_vac_deadline = self._now + self.cfg.vacuum_timeout_ms / 1000.0
            if self.vacuum_ok:
                self.alarms.discard(Alarm.VACUUM_FAIL)
                self._t_vac_deadline = None
            elif self._t_vac_deadline is not None and self._now >= self._t_vac_deadline:
                self.alarms.add(Alarm.VACUUM_FAIL)     # 도달 실패
        else:
            # 해제 → blow-off 펄스 (delay 후 hold 만큼 ON)
            if self._prev_vacuum_cmd:                 # 방금 끔 → 펄스 시작
                self._blowoff_phase = 1
                self._t_blowoff = self._now + self.cfg.blowoff_delay_ms / 1000.0
            self.out.vacuum_on = False
            self._run_blowoff()

        self._prev_vacuum_cmd = on

    def _run_blowoff(self) -> None:
        if self._blowoff_phase == 1 and self._now >= self._t_blowoff:
            self._blowoff_phase = 2
            self._t_blowoff = self._now + self.cfg.blowoff_hold_ms / 1000.0
        if self._blowoff_phase == 2:
            self.out.blow_off_on = True
            if self._now >= self._t_blowoff:
                self._blowoff_phase = 0
                self.out.blow_off_on = False
        else:
            self.out.blow_off_on = False

    # ----------------------------------------------------------------- 타워
    def _update_tower(self) -> None:
        o = self.out
        o.tower_green = o.tower_yellow = o.tower_red = o.tower_buzzer = False
        blink = int(self._now * 2) % 2 == 0     # ~0.5s 점멸

        s = self.state
        if s is State.SAFETY_STOP:
            o.tower_red = blink
            o.tower_buzzer = blink
        elif s is State.ERROR or self.alarms:
            o.tower_red = True
            o.tower_buzzer = blink
        elif s in (State.AUTO_MOVE_DOWN, State.AUTO_DWELL_DOWN, State.AUTO_MOVE_UP,
                   State.AUTO_DWELL_UP, State.AUTO_COUNT_UPDATE, State.AUTO_PRECHECK):
            o.tower_green = blink            # 운전 중 점멸
        elif s is State.AUTO_COMPLETE:
            o.tower_green = True
        elif s is State.MANUAL_IDLE:
            o.tower_yellow = blink
        else:  # AUTO_IDLE / BOOT
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
    def _start_move(self, state: State) -> None:
        self.state = state
        self._t_deadline = self._now + self.cfg.move_timeout_ms / 1000.0

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
