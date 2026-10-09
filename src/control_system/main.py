import logging
import os
import subprocess
import sys
from logging.handlers import MemoryHandler, RotatingFileHandler
from os import environ

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from .config import Config, RecipeStore, RuntimeSettings
from .core.controller import Controller
from .hardware.adam4017 import Adam4017
from .hardware.adam4055 import Adam4055
from .hardware.loadcell import LoadCell
from .hardware.modbus_hub import ModbusHub
from .hardware.signals import IO, DI1, DI2
from .hardware.touch_watch import TouchWatch
from .ui.logging_csv import CsvLogger, EventLog
from .ui.main_window import MainWindow

SETTINGS_PATH = "settings.json"
RECIPES_PATH = "recipes.json"
RUN_LOG_PATH = "data/run_log.csv"
APP_LOG_PATH = "data/app.log"
LOG_FLUSH_S = int(environ.get("LOG_FLUSH_S", "600"))   # 로그를 flash 로 덤프하는 주기(초, 기본 10분)
# 터치 먹통 복구용 OS 레벨 리셋 스크립트(현장 설치, sudo NOPASSWD). deploy/reset-touch.sh 참고.
TOUCH_RESET_CMD = environ.get("TOUCH_RESET_CMD", "/usr/local/bin/reset-touch.sh")

_mem_handler = None   # RAM 버퍼 핸들러 (flush_logs 에서 파일로 덤프)


def _setup_logging() -> None:
    """앱 로그를 data/app.log 에 저장(+stderr). 잡아먹힌 예외/통신 오류·사용자 동작 추적용.

    SD(flash) 쓰기 횟수를 줄이려 RAM 버퍼(MemoryHandler)에 모았다가 주기적으로만
    파일에 덤프한다(기본 10분, LOG_FLUSH_S). ERROR 이상은 즉시 덤프(진단 유실 방지),
    INFO/WARNING(사용자 동작·상태)은 버퍼링 후 일괄 기록. stderr(journald)는 실시간(휘발).
    """
    os.makedirs("data", exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    fh = RotatingFileHandler(APP_LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    global _mem_handler
    _mem_handler = MemoryHandler(capacity=10000, flushLevel=logging.ERROR, target=fh)
    root.addHandler(_mem_handler)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(sh)


def flush_logs() -> None:
    """RAM 버퍼의 로그를 파일(flash)로 즉시 덤프. (10분 타이머·앱 종료·USB 내보내기 시 호출)"""
    if _mem_handler is not None:
        _mem_handler.flush()


def _make_touch_reset(cfg):
    """터치 USB 재설정 콜백. mock/개발에선 로그만, 실기에선 sudo 스크립트 실행."""
    def reset() -> None:
        flush_logs()                        # 리셋 전 로그 보존
        if cfg.mock_hardware:
            logging.getLogger("event").warning("터치 USB 재설정(mock) — 실기에선 %s 실행", TOUCH_RESET_CMD)
            return
        try:
            subprocess.run(["sudo", "-n", TOUCH_RESET_CMD], timeout=8,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logging.getLogger("event").warning("터치 USB 재설정 실행: %s", TOUCH_RESET_CMD)
        except Exception:
            logging.getLogger("ctrl").exception("터치 리셋 스크립트 실패: %s", TOUCH_RESET_CMD)
    return reset


def _make_touch_recover(hub):
    """터치 먹통 복구(수동 제스처용) — 앱을 재실행(re-exec)해 터치를 되살린다.

    현장에서 sudo·노트북·flash 없이 **물리버튼 제스처만으로** 복구하기 위한 수단.
    터치 프리즈(컴포지터 stuck-touch)·USB 재열거 어느 쪽이든, 프로세스를 새로 띄우면
    Wayland 터치 연결이 새로 맺어져 복구된다(실측: 재시작 후 터치 정상화).

    주의: 자동 운전 중 발동하면 사이클이 끊기고 진공이 잠깐 OFF·카운트 초기화된다.
    수동 제스처(작업자 의도)로만 호출되므로 자동 감시에서는 쓰지 않는다.
    """
    def recover() -> None:
        logging.getLogger("event").warning("터치 복구 제스처 → 앱 재실행(re-exec)")
        flush_logs()                     # 재실행 전 로그 보존
        try:
            hub.close()                  # 시리얼 포트를 닫아 새 프로세스가 다시 열 수 있게
        except Exception:                # noqa: BLE001
            pass
        try:
            os.execv(sys.executable, [sys.executable, "-m", "control_system"])
        except Exception:                # noqa: BLE001  (re-exec 실패 시 systemd 재시작 유도)
            logging.getLogger("ctrl").exception("re-exec 실패 — 종료로 systemd 재시작 유도")
            os._exit(1)
    return recover


def _resolve_serial_port(cfg: Config) -> str:
    """실 시리얼 포트 자동 탐색. USB 재열거로 ttyUSB0↔1 이 바뀌어도 안정적으로 찾는다.

    우선순위: CP210x by-id(고정) → 지정 경로 → ttyUSB*. (socket:// URL 은 그대로 둔다.)
    """
    port = cfg.serial_port
    if cfg.mock_hardware or "://" in port:
        return port
    import glob
    import os
    byid = sorted(glob.glob("/dev/serial/by-id/*CP210*")) or sorted(glob.glob("/dev/serial/by-id/*ADAM*"))
    if byid:
        return byid[0]
    if os.path.exists(port):
        return port
    tty = sorted(glob.glob("/dev/ttyUSB*"))
    return tty[0] if tty else port


def build_io_stack(cfg: Config):
    """config 에 따라 시리얼 허브 + ADAM 모듈 + IO 파사드 + 로드셀을 조립한다."""
    hub = ModbusHub(
        _resolve_serial_port(cfg),
        cfg.baudrate,
        parity=cfg.parity,
        stopbits=cfg.stopbits,
        bytesize=cfg.bytesize,
        timeout_ms=cfg.timeout_ms,
        retries=cfg.retries,
        mock=cfg.mock_hardware,
    )
    hub.connect()
    a1 = Adam4055(hub, cfg.node_adam1, mock=cfg.mock_hardware, name="#1")
    a2 = Adam4055(hub, cfg.node_adam2, mock=cfg.mock_hardware, name="#2")
    ai = Adam4017(hub, cfg.node_adam4017, mock=cfg.mock_hardware)
    invert = set()
    if cfg.invert_vacuum_ok:
        invert.add(DI2.VACUUM_OK)
    if cfg.invert_mode_auto:
        invert.add(DI1.MODE_AUTO)
    io = IO(a1, a2, ai, input_invert=invert)
    loadcell = LoadCell(
        ai, cfg.loadcell_ai_channel, cfg.loadcell_full_scale_kgf, cfg.loadcell_calibration_path
    )
    return hub, a1, a2, ai, io, loadcell


def main() -> int:
    _setup_logging()
    logging.getLogger("boot").info("control-system 시작")
    cfg = Config.from_env()
    app = QApplication(sys.argv)
    app.setApplicationName("Control System")

    hub, a1, a2, ai, io, loadcell = build_io_stack(cfg)
    settings = RuntimeSettings.load(SETTINGS_PATH, cfg)   # 재부팅 시 파라미터만 복원
    recipes = RecipeStore.load(RECIPES_PATH)              # 운전 조건 레시피 3슬롯
    controller = Controller(cfg, io, loadcell, settings=settings)
    # 터치 먹통 복구 제스처(수동, 물리버튼): 앱 재실행으로 Qt 터치 연결을 새로 맺어 복구.
    # sudo·노트북·flash 불필요. (sudo 설치형 USB 재설정 _make_touch_reset 는 보조 수단으로 유지)
    controller.set_touch_reset_callback(_make_touch_recover(hub))
    logger = CsvLogger(RUN_LOG_PATH)
    events = EventLog()
    window = MainWindow(cfg, controller, a1, a2, ai, logger,
                        settings_path=SETTINGS_PATH, event_log=events, hub=hub,
                        recipes=recipes)

    # 로그 flash 덤프: LOG_FLUSH_S(기본 10분)마다 RAM 버퍼를 파일로. 종료 시에도 덤프.
    log_timer = QTimer()
    log_timer.timeout.connect(flush_logs)
    log_timer.start(LOG_FLUSH_S * 1000)
    app.aboutToQuit.connect(flush_logs)
    app._log_timer = log_timer          # GC 방지

    # 터치 USB 재열거(재접속) 자동 감시 → 카운트(상단바 노란 배지) + 자동 복구(터치 USB 재설정).
    # sudo 불필요(감지는 /sys 읽기만). 실제 USB 재설정은 reset-touch.sh 설치 시에만 동작.
    if not cfg.mock_hardware:
        # 감지·카운트만(무인 자동 재시작 안 함 — 운전 중 진공/카운트 보호). 복구는 수동 제스처로.
        touch_watch = TouchWatch(environ.get("TOUCH_VIDPID", "0eef:0005"))

        def _poll_touch() -> None:
            touch_watch.poll()
            controller.touch_reenum_count = touch_watch.count

        touch_timer = QTimer()
        touch_timer.timeout.connect(_poll_touch)
        touch_timer.start(int(environ.get("TOUCH_WATCH_MS", "1000")))
        app._touch_timer = touch_timer  # GC 방지

    # KIOSK=1 이면 mock 이라도 전체화면(장비/파이 터치스크린용, 트레이·타이틀바 덮음).
    kiosk = environ.get("KIOSK", "0") == "1"

    def _show_fullscreen(w) -> None:
        # 일부 Wayland 컴포지터(labwc)에서 fullscreen 이 출력 크기로 고정되지 않아
        # 창이 화면보다 커지는 문제가 있어, 화면 크기로 상한을 강제한다(네비 잘림 방지).
        scr = app.primaryScreen().geometry()
        w.setMaximumSize(scr.width(), scr.height())
        w.resize(scr.width(), scr.height())
        w.showFullScreen()

    def show_main() -> None:
        if cfg.mock_hardware and not kiosk:
            window.resize(1024, 600)   # 노트북 개발: 창 모드
            window.move(0, 0)
            window.show()
            # mock 제어함 시뮬레이터(별도 창): 외부 스위치 클릭 + 센서/인터록 시뮬 +
            # 출력 램프. DEBUG_IO=0 으로 끔. (원 I/O 디버그 창은 debug_window.py 로 유지)
            if environ.get("DEBUG_IO", "1") == "1":
                from .ui.control_panel import ControlPanel
                panel = ControlPanel(controller, a1, a2, ai)
                panel.move(1030, 0)
                panel.show()
                window.destroyed.connect(panel.close)
                window._panel = panel      # GC 방지
        else:
            _show_fullscreen(window)
        if getattr(app, "_boot", None) is not None:
            app._boot.close()
            app._boot = None

    # 부팅 화면(BOOT=0 으로 끔). 완료 후 메인 창 표시.
    app._boot = None
    if environ.get("BOOT", "1") == "1":
        from .ui.boot_screen import BootScreen
        boot = BootScreen(on_done=show_main)
        app._boot = boot
        if cfg.mock_hardware and not kiosk:
            boot.resize(1024, 600); boot.show()
        else:
            _show_fullscreen(boot)
    else:
        show_main()

    try:
        return app.exec()
    finally:
        flush_logs()        # 종료 시 남은 로그를 파일로
        hub.close()
