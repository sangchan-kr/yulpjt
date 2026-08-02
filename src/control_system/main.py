import sys
from os import environ

from PySide6.QtWidgets import QApplication

from .config import Config, RuntimeSettings
from .core.controller import Controller
from .hardware.adam4017 import Adam4017
from .hardware.adam4055 import Adam4055
from .hardware.loadcell import LoadCell
from .hardware.modbus_hub import ModbusHub
from .hardware.signals import IO, DI2
from .ui.logging_csv import CsvLogger, EventLog
from .ui.main_window import MainWindow

SETTINGS_PATH = "settings.json"
RUN_LOG_PATH = "data/run_log.csv"


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
    invert = {DI2.VACUUM_OK} if cfg.invert_vacuum_ok else frozenset()
    io = IO(a1, a2, ai, input_invert=invert)
    loadcell = LoadCell(
        ai, cfg.loadcell_ai_channel, cfg.loadcell_full_scale_kgf, cfg.loadcell_calibration_path
    )
    return hub, a1, a2, ai, io, loadcell


def main() -> int:
    cfg = Config.from_env()
    app = QApplication(sys.argv)
    app.setApplicationName("Control System")

    hub, a1, a2, ai, io, loadcell = build_io_stack(cfg)
    settings = RuntimeSettings.load(SETTINGS_PATH, cfg)   # 재부팅 시 파라미터만 복원
    controller = Controller(cfg, io, loadcell, settings=settings)
    logger = CsvLogger(RUN_LOG_PATH)
    events = EventLog()
    window = MainWindow(cfg, controller, a1, a2, ai, logger,
                        settings_path=SETTINGS_PATH, event_log=events, hub=hub)

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
        hub.close()
