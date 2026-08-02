"""IO 테스트 패널 — 노트북에서 파이 실 하드웨어를 직접 제어 (컨트롤러 우회).

파이의 serial_bridge.py(TCP↔/dev/ttyUSB0)에 socket:// 로 접속.
사용: python io_test_panel.py [PI_IP] [PORT]
"""
import sys
sys.path.insert(0, r"C:\Users\Sangchan Na\Projects\yulpjt\src")

PI_IP = sys.argv[1] if len(sys.argv) > 1 else "192.168.137.151"
PORT = sys.argv[2] if len(sys.argv) > 2 else "20108"
URL = f"socket://{PI_IP}:{PORT}"

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton,
    QVBoxLayout, QWidget,
)
from control_system.hardware.modbus_hub import AdamSerialBus, AdamCommError
from control_system.hardware.adam4055 import Adam4055
from control_system.hardware.adam4017 import Adam4017

DI1 = ["자동모드", "자동시작", "자동정지", "수동상승", "수동하강", "상승위치", "하강위치", "구동허가"]
DO1 = ["시작램프", "정지램프", "상승램프", "하강램프", "하강밸브", "상승밸브", "부저", "예비"]
DI2 = ["진공확인", "파기확인", "에어압", "진공알람", "예비4", "예비5", "예비6", "예비7"]
DO2 = ["진공(흡착)", "파기(blow)", "예비2", "예비3", "예비4", "예비5", "예비6", "예비7"]
DO1_ACT = {4, 5}        # 하강/상승 밸브 (경고)
DO2_ACT = {0, 1}        # 진공/파기 (경고)


class Panel(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"IO 테스트 패널 — 실 하드웨어 ({PI_IP})")
        self.resize(900, 620)
        self.hub = AdamSerialBus(URL, 9600, mock=False, timeout_ms=600, retries=1)
        ok = False
        try:
            ok = self.hub.connect()
        except Exception as e:
            self._fatal(f"브리지 접속 실패: {e}\n파이에서 serial_bridge.py 가 떠 있는지 확인.")
            return
        self.a1 = Adam4055(self.hub, 1, name="press")
        self.a2 = Adam4055(self.hub, 2, name="vac")
        self.ai = Adam4017(self.hub, 3)

        root = QVBoxLayout(self)
        self._status = QLabel(f"접속: {ok}  {URL}")
        self._status.setStyleSheet("font-weight:800;")
        root.addWidget(self._status)

        cols = QHBoxLayout()
        cols.addWidget(self._module_box("ADAM #1 프레스/스위치 (주소 1)", self.a1, DI1, DO1, DO1_ACT, "1"))
        cols.addWidget(self._module_box("ADAM #2 진공 (주소 2)", self.a2, DI2, DO2, DO2_ACT, "2"))
        root.addLayout(cols)

        self._ai_lbl = QLabel("로드셀: -")
        self._ai_lbl.setStyleSheet("font-size:18px; font-weight:900;")
        root.addWidget(self._ai_lbl)

        # 초기 DO 상태 동기화 (출력 건드리지 않음)
        self._sync_initial()

        self._timer = QTimer(self); self._timer.timeout.connect(self._poll); self._timer.start(300)

    def _fatal(self, msg):
        v = QVBoxLayout(self)
        lbl = QLabel(msg); lbl.setStyleSheet("color:#c0392b; font-weight:800; font-size:14px;")
        lbl.setWordWrap(True); v.addWidget(lbl)

    def _module_box(self, title, mod, di_lbl, do_lbl, act, key):
        box = QGroupBox(title); g = QVBoxLayout(box)
        # DI 표시
        dih = QLabel("입력 (DI) — 실시간"); dih.setStyleSheet("font-weight:800;"); g.addWidget(dih)
        digrid = QGridLayout()
        setattr(self, f"_di{key}", [])
        for ch in range(8):
            lamp = QLabel(f"{ch} {di_lbl[ch]}")
            lamp.setStyleSheet(self._di_style(False))
            getattr(self, f"_di{key}").append(lamp)
            digrid.addWidget(lamp, ch // 2, ch % 2)
        g.addLayout(digrid)
        # DO 토글
        doh = QLabel("출력 (DO) — 클릭하면 즉시 ON/OFF"); doh.setStyleSheet("font-weight:800; margin-top:6px;"); g.addWidget(doh)
        dogrid = QGridLayout()
        setattr(self, f"_do{key}", [])
        for ch in range(8):
            b = QPushButton(f"{ch} {do_lbl[ch]}")
            b.setCheckable(True); b.setMinimumHeight(38)
            if ch in act:
                b.setStyleSheet("QPushButton{background:#fbe3e3;border:1px solid #d1352b;font-weight:800;}"
                                "QPushButton:checked{background:#d1352b;color:#fff;}")
            else:
                b.setStyleSheet("QPushButton:checked{background:#22a35a;color:#fff;font-weight:800;}")
            b.toggled.connect(lambda on, m=mod, c=ch: self._set_do(m, c, on))
            getattr(self, f"_do{key}").append(b)
            dogrid.addWidget(b, ch // 2, ch % 2)
        g.addLayout(dogrid)
        return box

    @staticmethod
    def _di_style(on):
        bg = "#22a35a" if on else "#e6ebf1"; fg = "#fff" if on else "#7a8896"
        return f"background:{bg}; color:{fg}; padding:6px 8px; border-radius:5px; font-weight:700;"

    def _sync_initial(self):
        for mod, key in ((self.a1, "1"), (self.a2, "2")):
            try:
                do = mod.read_do()
                for ch in range(8):
                    mod.stage_do(ch, do[ch])
                    b = getattr(self, f"_do{key}")[ch]
                    b.blockSignals(True); b.setChecked(do[ch]); b.blockSignals(False)
            except Exception:
                pass

    def _set_do(self, mod, ch, on):
        try:
            mod.stage_do(ch, on); mod.flush_do()
            self._status.setText(f"DO 쓰기: {mod.name} ch{ch} = {'ON' if on else 'OFF'}")
        except Exception as e:
            self._status.setText(f"DO 쓰기 오류: {e}")

    def _reconnect(self):
        try:
            self.hub.close()
        except Exception:
            pass
        self.hub._ser = None
        try:
            ok = self.hub.connect()
            self._status.setText(f"재접속 {'성공' if ok else '실패'}  {URL}")
        except Exception as e:
            self._status.setText(f"재접속 시도… ({e})")

    def _poll(self):
        try:
            for mod, key in ((self.a1, "1"), (self.a2, "2")):
                di = mod.read_di()
                for ch in range(8):
                    getattr(self, f"_di{key}")[ch].setStyleSheet(self._di_style(di[ch]))
            ma = self.ai.read_ma(0)
            self._ai_lbl.setText(f"로드셀 ch0: {ma:.3f} mA   (≈ 하중 {(ma-4.0)/16.0*1000:.0f} kgf, 무보정)")
            self._fail = 0
        except Exception as e:
            self._fail = getattr(self, "_fail", 0) + 1
            self._status.setText(f"통신 오류({self._fail}): {e} — 재접속 시도 중…")
            if self._fail >= 3:
                self._reconnect()
                self._fail = 0


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = Panel(); w.show()
    sys.exit(app.exec())
