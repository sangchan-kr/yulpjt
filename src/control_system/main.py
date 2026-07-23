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


def build_io_stack(cfg: Config):
    """config 에 따라 Modbus 허브 + ADAM 모듈 + IO 파사드 + 로드셀을 조립한다."""
    hub = ModbusHub(
        cfg.serial_port,
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
    debug_win = None
    if cfg.mock_hardware and not kiosk:
        window.resize(1024, 600)   # 노트북 개발: 창 모드
        window.move(0, 0)
        window.show()
        # mock 디버그 창(별도): DI 주입 + DO 관찰 + 로드셀 슬라이더. DEBUG_IO=0 로 끌 수 있음.
        if environ.get("DEBUG_IO", "1") == "1":
            from .ui.debug_window import DebugWindow
            debug_win = DebugWindow(controller, a1, a2, ai)
            debug_win.move(1030, 0)
            debug_win.show()
            window.destroyed.connect(debug_win.close)
    else:
        # 장비/키오스크: 전체화면. 일부 Wayland 컴포지터(labwc)에서 fullscreen 이
        # 출력 크기로 고정되지 않아 창이 화면보다 커지는 문제가 있어, 화면 크기로
        # 상한을 강제해 하단 네비가 잘리지 않게 한다.
        scr = app.primaryScreen().geometry()
        window.setMaximumSize(scr.width(), scr.height())
        window.resize(scr.width(), scr.height())
        window.showFullScreen()

    try:
        return app.exec()
    finally:
        hub.close()
