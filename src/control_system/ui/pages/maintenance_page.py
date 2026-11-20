"""유지보수 / 입출력 시험 페이지 (관리자, 목업 v0.4 / handoff §15).

좌: 진공/파기 hold-to-run 시험 + DO 시험.  우: 하중/통신 점검(교정·재연결·저장).
화면 이탈 시 모든 시험 출력을 OFF 한다(main_window 에서 on_leave 호출).
"""

import datetime
import glob
import logging
import os
import shutil
import subprocess

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from ...core.states import State
from ...hardware.signals import AI, DO1
from .. import theme
from ..keypad import edit_number

_IDLE = {State.AUTO_IDLE, State.MANUAL_IDLE, State.AUTO_COMPLETE}

# HMI 시간설정 → 시스템 시간을 바꾸려면 root 가 필요하므로 sudo NOPASSWD 헬퍼를 통한다.
# deploy/set-time.sh + /etc/sudoers.d/set-time (firstrun 또는 수동 설치).
_SET_TIME = "/usr/local/bin/set-time.sh"
_TIME_FIELDS = [("year", "년", 4), ("month", "월", 2), ("day", "일", 2),
                ("hour", "시", 2), ("minute", "분", 2)]

_HOLD_BLUE = ("background:#e7effd; border:1px solid #4b86e8; color:#1c50ac;"
              "border-radius:9px; font-weight:800; padding:12px;")
_HOLD_YEL = ("background:#fdf1d8; border:1px solid #e0a83c; color:#8a5a12;"
             "border-radius:9px; font-weight:800; padding:12px;")


def _stat(title: str) -> tuple[QFrame, QLabel]:
    f = QFrame(); f.setObjectName("stat")
    v = QVBoxLayout(f); v.setContentsMargins(11, 8, 11, 8); v.setSpacing(2)
    t = QLabel(title); t.setObjectName("statLabel")
    val = QLabel("-"); val.setObjectName("statValue")
    v.addWidget(t); v.addWidget(val)
    return f, val


class MaintenancePage(QWidget):
    def __init__(self, controller, loadcell, hub, run_log_path: str) -> None:
        super().__init__()
        self.ctrl = controller
        self.loadcell = loadcell
        self.hub = hub
        self.run_log_path = run_log_path

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10); root.setSpacing(8)
        title = QLabel("유지보수 및 입출력 시험"); title.setObjectName("pageTitle")
        root.addWidget(title)

        body = QHBoxLayout(); body.setSpacing(12)
        body.addWidget(self._vacuum_card(), 1)
        body.addWidget(self._service_card(), 1)
        body.addWidget(self._time_card(), 1)
        root.addLayout(body, 1)

    # ---------------------------------------------------------------- 진공/파기
    def _vacuum_card(self) -> QFrame:
        card = QFrame(); card.setObjectName("card")
        lay = QVBoxLayout(card); lay.setContentsMargins(14, 12, 14, 12); lay.setSpacing(8)
        head = QLabel("진공 및 파기 시험"); head.setObjectName("cardTitle")
        lay.addWidget(head)

        warn = QLabel("시험 출력은 누르는 동안만 동작. 화면 벗어나면 꺼짐.")
        warn.setWordWrap(True)
        warn.setStyleSheet("background:#fdf1d8; border:1px solid #ecd39a; border-radius:8px;"
                           "color:#8a5a12; padding:7px 10px; font-weight:700;")
        lay.addWidget(warn)

        row = QHBoxLayout(); row.setSpacing(10)
        fc, self._vac_cmd = _stat("진공 명령")
        fo, self._vac_ok = _stat("진공 확인")
        row.addWidget(fc); row.addWidget(fo)
        lay.addLayout(row)

        # 홀드 버튼 2개를 한 줄로(공간 절약). 누르는 동안만 동작.
        holdrow = QHBoxLayout(); holdrow.setSpacing(8)
        self._b_vac = QPushButton("진공 켜기")
        self._b_vac.setStyleSheet(_HOLD_BLUE); self._b_vac.setMinimumHeight(46)
        self._b_vac.pressed.connect(lambda: self.ctrl.set_vacuum(True))
        self._b_vac.released.connect(lambda: self.ctrl.set_vacuum(False))
        self._b_blow = QPushButton("파기")
        self._b_blow.setStyleSheet(_HOLD_YEL); self._b_blow.setMinimumHeight(46)
        self._b_blow.pressed.connect(lambda: self.ctrl.request_maintenance_blowoff(True))
        self._b_blow.released.connect(lambda: self.ctrl.request_maintenance_blowoff(False))
        holdrow.addWidget(self._b_vac); holdrow.addWidget(self._b_blow)
        lay.addLayout(holdrow)

        head2 = QLabel("DO 시험 (버튼램프/부저)"); head2.setObjectName("cardTitle")
        lay.addWidget(head2)
        grid = QGridLayout(); grid.setHorizontalSpacing(8); grid.setVerticalSpacing(6)
        self._do_btns = {}
        names = {DO1.LAMP_AUTO_START: "시작 램프", DO1.LAMP_AUTO_STOP: "정지 램프",
                 DO1.LAMP_MANUAL_UP: "상승 램프", DO1.LAMP_MANUAL_DOWN: "하강 램프",
                 DO1.BUZZER: "부저"}
        for i, sig in enumerate((DO1.LAMP_AUTO_START, DO1.LAMP_AUTO_STOP,
                                 DO1.LAMP_MANUAL_UP, DO1.LAMP_MANUAL_DOWN, DO1.BUZZER)):
            b = QPushButton(names[sig]); b.setCheckable(True); b.setMinimumHeight(34)
            b.setStyleSheet("font-size:14px;")
            b.toggled.connect(lambda on, s=sig: self.ctrl.set_do_override(s, on))
            self._do_btns[sig] = b
            grid.addWidget(b, i // 2, i % 2)
        lay.addLayout(grid)
        lay.addStretch(1)
        return card

    # ---------------------------------------------------------------- 시스템 시간
    def _time_card(self) -> QFrame:
        card = QFrame(); card.setObjectName("card")
        lay = QVBoxLayout(card); lay.setContentsMargins(14, 12, 14, 12); lay.setSpacing(8)
        head = QLabel("시스템 시간"); head.setObjectName("cardTitle")
        lay.addWidget(head)

        self._time_now = QLabel("현재: -")
        self._time_now.setStyleSheet("font-weight:900; color:#1b2735; font-size:17px;")
        lay.addWidget(self._time_now)
        info = QLabel("오프라인이라 자동 동기화가 안 됩니다. 값을 입력하고 적용하세요.")
        info.setWordWrap(True); info.setStyleSheet("color:#7a8896; font-size:12px;")
        lay.addWidget(info)

        self._t_vals: dict[str, int] = {}
        self._t_boxes: dict[str, QLabel] = {}
        g = QGridLayout(); g.setHorizontalSpacing(8); g.setVerticalSpacing(8)
        for idx, (key, label, _w) in enumerate(_TIME_FIELDS):
            r, c = divmod(idx, 3)
            cell = QVBoxLayout(); cell.setSpacing(2)
            lbl = QLabel(label); lbl.setStyleSheet("color:#5b6b7f; font-weight:700; font-size:12px;")
            box = QLabel("-")
            box.setStyleSheet("background:#ffffff; border:1px solid #cfd8e2; border-radius:8px;"
                              "padding:8px 6px; font-weight:900; color:#1b2735; font-size:16px;")
            box.setAlignment(Qt.AlignmentFlag.AlignCenter); box.setMinimumWidth(62); box.setFixedHeight(42)
            box.mousePressEvent = lambda _e, k=key, l=label: self._edit_time_field(k, l)
            self._t_boxes[key] = box
            cell.addWidget(lbl); cell.addWidget(box)
            w = QWidget(); w.setLayout(cell)
            g.addWidget(w, r, c)
        lay.addLayout(g)

        self._b_time = QPushButton("이 시간으로 설정")
        self._b_time.setObjectName("primary"); self._b_time.setMinimumHeight(46)
        self._b_time.clicked.connect(self._set_system_time)
        lay.addWidget(self._b_time)

        self._time_msg = QLabel("")
        self._time_msg.setWordWrap(True)
        self._time_msg.setStyleSheet(f"color:{theme.GREEN}; font-weight:700;")
        lay.addWidget(self._time_msg)
        lay.addStretch(1)
        self._prefill_time()
        return card

    def _prefill_time(self) -> None:
        n = datetime.datetime.now()
        self._t_vals = {"year": n.year, "month": n.month, "day": n.day,
                        "hour": n.hour, "minute": n.minute}
        self._refresh_time_boxes()

    def _refresh_time_boxes(self) -> None:
        for key, _label, w in _TIME_FIELDS:
            self._t_boxes[key].setText(f"{self._t_vals.get(key, 0):0{w}d}")

    def _edit_time_field(self, key: str, label: str) -> None:
        new = edit_number(self, f"{label} 입력", self._t_vals.get(key, 0), is_float=False)
        if new is None:
            return
        self._t_vals[key] = int(new)
        self._refresh_time_boxes()

    def _set_system_time(self) -> None:
        try:
            dt = datetime.datetime(self._t_vals["year"], self._t_vals["month"],
                                   self._t_vals["day"], self._t_vals["hour"],
                                   self._t_vals["minute"], 0)
        except (ValueError, KeyError):
            self._time_msg.setStyleSheet("color:#b1291f; font-weight:700;")
            self._time_msg.setText("날짜/시간 값이 올바르지 않습니다.")
            return
        ts = dt.strftime("%Y-%m-%d %H:%M:%S")
        if getattr(self.ctrl.cfg, "mock_hardware", False):
            self._time_msg.setStyleSheet(f"color:{theme.GREEN}; font-weight:700;")
            self._time_msg.setText(f"[개발모드] 실제 설정 생략: {ts}")
            return
        try:
            r = subprocess.run(["sudo", "-n", _SET_TIME, ts], timeout=8,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if r.returncode == 0:
                self._time_msg.setStyleSheet(f"color:{theme.GREEN}; font-weight:700;")
                self._time_msg.setText(f"시간 설정됨: {ts}")
                logging.getLogger("event").warning("사용자: 시스템 시간 설정 → %s", ts)
            else:
                self._time_msg.setStyleSheet("color:#b1291f; font-weight:700;")
                self._time_msg.setText("설정 실패: 헬퍼(set-time.sh) 미설치/권한. 관리자 설치 필요.")
        except Exception as e:  # noqa: BLE001
            self._time_msg.setStyleSheet("color:#b1291f; font-weight:700;")
            self._time_msg.setText(f"설정 실패: {e}")

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # 유지보수 화면을 열 때마다 입력칸을 현재 시각으로 채운다.
        try:
            self._prefill_time()
            self._time_msg.setText("")
        except Exception:  # noqa: BLE001
            pass

    # ---------------------------------------------------------------- 하중/통신
    def _service_card(self) -> QFrame:
        card = QFrame(); card.setObjectName("card")
        lay = QVBoxLayout(card); lay.setContentsMargins(14, 12, 14, 12); lay.setSpacing(8)
        head = QLabel("하중 및 통신 점검"); head.setObjectName("cardTitle")
        lay.addWidget(head)

        g = QGridLayout(); g.setSpacing(10)
        f1, self._raw = _stat("로드셀 원신호")
        f2, self._load = _stat("보정 하중")
        f3, self._zero = _stat("영점 보정값")
        f4, self._scale = _stat("배율 보정값")
        g.addWidget(f1, 0, 0); g.addWidget(f2, 0, 1)
        g.addWidget(f3, 1, 0); g.addWidget(f4, 1, 1)
        lay.addLayout(g)

        grid = QGridLayout(); grid.setSpacing(8)
        b_zero = QPushButton("하중 영점"); b_zero.clicked.connect(self._load_zero)
        b_span = QPushButton("배율 교정"); b_span.clicked.connect(self._span)
        b_reconn = QPushButton("통신 재연결"); b_reconn.clicked.connect(self._reconnect)
        b_export = QPushButton("USB로 저장"); b_export.clicked.connect(self._export_usb)
        for i, b in enumerate((b_zero, b_span, b_reconn, b_export)):
            b.setMinimumHeight(46)
            grid.addWidget(b, i // 2, i % 2)
        lay.addLayout(grid)

        self._perm = QLabel("출력 허가: -")
        self._perm.setStyleSheet("font-weight:700; color:#3a4a5c;")
        lay.addWidget(self._perm)

        self._msg = QLabel("")
        self._msg.setStyleSheet(f"color:{theme.GREEN}; font-weight:700;")
        self._msg.setWordWrap(True)
        lay.addWidget(self._msg)
        lay.addStretch(1)
        return card

    # ---------------------------------------------------------------- actions
    def _load_zero(self) -> None:
        self.ctrl.cmd_load_zero()
        self._msg.setText("하중 영점 요청됨(무부하 상태에서 실행).")

    def _span(self) -> None:
        if self.ctrl.state not in _IDLE:
            self._msg.setText("대기 상태에서만 교정할 수 있습니다.")
            return
        known = edit_number(self, "기준 하중(kgf)", 100.0, is_float=True)
        if known is None:
            return
        ok = self.loadcell.calibrate_span(float(known))
        self._msg.setText(f"배율 교정 {'완료' if ok else '실패(측정값 확인)'} — 배율={self.loadcell.scale:.4f}")

    def _reconnect(self) -> None:
        try:
            self.hub.connect()
            self._msg.setText("통신 재연결 시도 완료.")
        except Exception as e:  # noqa: BLE001
            self._msg.setText(f"재연결 실패: {e}")

    @staticmethod
    def _find_usb_mount():
        """쓰기 가능한 이동식(USB) 마운트 경로를 찾는다. 없으면 None."""
        cands = []
        if os.name == "nt":                       # 개발(Windows): 이동식 드라이브만
            import ctypes
            import string
            DRIVE_REMOVABLE = 2
            for d in string.ascii_uppercase:
                root = f"{d}:\\"
                try:
                    if ctypes.windll.kernel32.GetDriveTypeW(root) == DRIVE_REMOVABLE:
                        cands.append(root)
                except Exception:  # noqa: BLE001
                    pass
        else:                                     # 파이/리눅스: 자동 마운트 위치
            for pat in ("/media/*/*", "/media/*", "/run/media/*/*", "/mnt/*"):
                cands += glob.glob(pat)
        for c in cands:
            if os.path.isdir(c) and os.access(c, os.W_OK):
                return c
        return None

    def _export_usb(self) -> None:
        """로그 버퍼를 파일로 덤프한 뒤, data 의 로그(app.log*·run_log*.csv)를 USB로 복사."""
        for h in logging.getLogger().handlers:    # RAM 버퍼(MemoryHandler) → 파일
            try:
                h.flush()
            except Exception:  # noqa: BLE001
                pass
        usb = self._find_usb_mount()
        if not usb:
            self._msg.setText("USB를 찾을 수 없습니다. USB 메모리를 꽂고 다시 누르세요.")
            return
        data_dir = os.path.dirname(self.run_log_path) or "data"
        files = sorted(glob.glob(os.path.join(data_dir, "app.log*"))) + \
            sorted(glob.glob(os.path.join(data_dir, "run_log*.csv")))
        if not files:
            self._msg.setText("내보낼 로그가 없습니다.")
            return
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        dst = os.path.join(usb, f"rpt-logs_{ts}")
        try:
            os.makedirs(dst, exist_ok=True)
            for f in files:
                shutil.copy2(f, dst)
            self._msg.setText(f"USB 저장 완료: {dst} ({len(files)}개)")
            logging.getLogger("event").info("사용자: USB 로그 내보내기 → %s", dst)
        except OSError as e:
            self._msg.setText(f"USB 저장 실패: {e}")

    def on_leave(self) -> None:
        """페이지 이탈 시 모든 시험 출력 OFF."""
        self.ctrl.set_vacuum(False)
        self.ctrl.request_maintenance_blowoff(False)
        self.ctrl.clear_do_overrides()
        for b in self._do_btns.values():
            b.blockSignals(True); b.setChecked(False); b.blockSignals(False)

    def update_view(self) -> None:
        c = self.ctrl
        self._vac_cmd.setText("켜짐" if c.vacuum_command else "꺼짐")
        self._vac_ok.setText("정상" if c.vacuum_ok else "꺼짐")
        # 컨트롤러가 스캔마다 캐시한 값 사용(추가 시리얼 읽기 안 함).
        self._raw.setText(f"{c.io.ma(AI.LOADCELL_CURRENT):.2f} mA")
        self._load.setText(f"{c.load_kgf:.1f} kgf")
        self._zero.setText(f"{self.loadcell.zero_offset:.1f} kgf")
        self._scale.setText(f"{self.loadcell.scale:.3f}")
        allowed, _reason = c.vacuum_permission()
        self._perm.setText(f"출력 허가: {'허용' if allowed else '차단'}")
        self._time_now.setText("현재: " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
