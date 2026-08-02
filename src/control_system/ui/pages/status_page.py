"""시스템 상태 페이지 (목업 v0.4 / handoff §11).

좌: 제어기/통신/프로세스 요약. 우: 입출력(탭 전환, 정렬 그리드) + 진공 출력 허가 상세.
"""

import logging
import shutil
import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QVBoxLayout, QWidget,
)

from ...hardware.signals import AI, DI1, DI2, DO1, DO2
from .. import theme

# 신호명 한글 표기 -----------------------------------------------------------
_DI1_KO = {0: "자동 모드", 1: "자동 시작", 2: "자동 정지", 3: "수동 상승",
           4: "수동 하강", 5: "상승 위치", 6: "하강 위치", 7: "구동 허가"}
_DO1_KO = {0: "시작 램프", 1: "정지 램프", 2: "상승 램프", 3: "하강 램프",
           4: "하강 밸브", 5: "상승 밸브", 6: "부저", 7: "예비"}
_DI2_KO = {0: "진공 확인", 1: "파기 확인", 2: "에어압 정상", 3: "진공기 알람",
           4: "예비", 5: "예비", 6: "예비", 7: "예비"}
_DO2_KO = {0: "진공 발생", 1: "파기 동작", 2: "예비", 3: "예비",
           4: "예비", 5: "예비", 6: "예비", 7: "예비"}
_AI_KO = {0: "로드셀 전류", 1: "예비", 2: "예비", 3: "예비",
          4: "예비", 5: "예비", 6: "예비", 7: "예비"}


def _read_cpu_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return int(f.read().strip()) / 1000.0
    except OSError:
        return None


def _box(title: str) -> tuple[QFrame, QLabel]:
    f = QFrame(); f.setObjectName("stat")
    v = QVBoxLayout(f); v.setContentsMargins(10, 5, 10, 5); v.setSpacing(1)
    t = QLabel(title); t.setObjectName("statLabel"); t.setStyleSheet("font-size:12px;")
    # 좁은 2열 박스라 값 폰트를 줄여 깨짐(넘침) 방지 (전역 statValue 19px 대신 16px).
    val = QLabel("-"); val.setStyleSheet("color:#1b2735; font-weight:800; font-size:16px;")
    v.addWidget(t); v.addWidget(val)
    return f, val


class StatusPage(QWidget):
    def __init__(self, controller, adam1, adam2, adam4017, start_monotonic: float) -> None:
        super().__init__()
        self.ctrl = controller
        self.a1, self.a2, self.ai = adam1, adam2, adam4017
        self._start = start_monotonic
        self._tab = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10); root.setSpacing(8)
        title = QLabel("시스템 상태"); title.setObjectName("pageTitle")
        root.addWidget(title)

        body = QHBoxLayout(); body.setSpacing(12)
        body.addWidget(self._summary_card(), 1)
        body.addWidget(self._io_card(), 1)
        root.addLayout(body, 1)

    # ---------------------------------------------------------------- 좌: 요약
    def _summary_card(self) -> QFrame:
        card = QFrame(); card.setObjectName("card")
        lay = QVBoxLayout(card); lay.setContentsMargins(14, 12, 14, 12); lay.setSpacing(8)
        head = QLabel("제어기 및 통신"); head.setObjectName("cardTitle")
        lay.addWidget(head)
        grid = QGridLayout(); grid.setHorizontalSpacing(10); grid.setVerticalSpacing(7)
        self._b = {}
        specs = [
            ("app", "제어 프로그램"), ("uptime", "연속 실행시간"),
            ("cpu", "CPU 온도"), ("storage", "저장공간 여유"),
            ("poll", "폴링 / 재시도"), ("mA", "로드셀 원신호"),
            ("vok", "진공 확인"),
        ]
        for i, (k, label) in enumerate(specs):
            f, val = _box(label)
            self._b[k] = val
            grid.addWidget(f, i // 2, i % 2)
        lay.addLayout(grid)

        # 입출력 모듈 3개 연결 상태를 신호등 램프로 한 줄에 (박스 3개 절약).
        modrow = QHBoxLayout(); modrow.setSpacing(12)
        cap = QLabel("모듈 연결"); cap.setObjectName("statLabel"); cap.setStyleSheet("font-size:13px;")
        modrow.addWidget(cap)
        self._mod_lamps = {}
        for key, name in (("m1", "입출력1"), ("m2", "입출력2"), ("ai", "아날로그")):
            dot = QLabel("●"); dot.setStyleSheet("color:#c8d0da; font-size:16px;")
            txt = QLabel(name); txt.setStyleSheet("font-size:13px; font-weight:700; color:#3a4a5c;")
            self._mod_lamps[key] = dot
            modrow.addWidget(dot); modrow.addWidget(txt)
        modrow.addStretch(1)
        lay.addLayout(modrow)

        head2 = QLabel("진공 출력 허가"); head2.setObjectName("cardTitle")
        lay.addWidget(head2)
        self._perm = QLabel("-")
        self._perm.setStyleSheet("font-size:14px; color:#3a4a5c; line-height:160%;")
        lay.addWidget(self._perm)
        lay.addStretch(1)
        return card

    # ---------------------------------------------------------------- 우: I/O
    def _io_card(self) -> QFrame:
        card = QFrame(); card.setObjectName("card")
        lay = QVBoxLayout(card); lay.setContentsMargins(14, 12, 14, 12); lay.setSpacing(8)
        tabs = QHBoxLayout()
        self._tabgroup = QButtonGroup(self); self._tabgroup.setExclusive(True)
        for i, name in enumerate(("입출력 1", "입출력 2", "아날로그")):
            b = QPushButton(name); b.setObjectName("tab"); b.setCheckable(True)
            b.clicked.connect(lambda _=False, idx=i: self._set_tab(idx))
            self._tabgroup.addButton(b, i)
            tabs.addWidget(b)
        tabs.addStretch(1)
        self._tabgroup.button(0).setChecked(True)
        lay.addLayout(tabs)

        self._io_grid = QGridLayout()
        self._io_grid.setHorizontalSpacing(10)
        self._io_grid.setVerticalSpacing(5)
        self._io_host = QWidget()
        self._io_host.setLayout(self._io_grid)
        lay.addWidget(self._io_host, 1)
        self._io_rows = []          # [(w, ...)] 재사용 위젯
        self._io_headers = []

        # 아날로그 탭 전용: A0-A1 / A2-A3 … 페어 박스. A0~3 전류(mA), A4~7 전압(V).
        self._ai_grid = QGridLayout()
        self._ai_grid.setHorizontalSpacing(10); self._ai_grid.setVerticalSpacing(8)
        self._ai_host = QWidget(); self._ai_host.setLayout(self._ai_grid)
        self._ai_boxes = []
        for i in range(8):
            title = "A0 로드셀(전류)" if i == 0 else f"A{i} {'전류' if i < 4 else '전압'}"
            f, val = _box(title)
            self._ai_boxes.append(val)
            self._ai_grid.addWidget(f, i // 2, i % 2)
        self._ai_grid.setColumnStretch(0, 1); self._ai_grid.setColumnStretch(1, 1)
        self._ai_grid.setRowStretch(4, 1)
        lay.addWidget(self._ai_host, 1)
        self._ai_host.hide()
        return card

    def _set_tab(self, idx: int) -> None:
        self._tab = idx

    # ---------------------------------------------------------------- 갱신
    def update_view(self) -> None:
        c = self.ctrl
        up = int(time.monotonic() - self._start)
        self._b["app"].setText("실행 중")
        self._b["uptime"].setText(f"{up // 3600:02d}:{up % 3600 // 60:02d}:{up % 60:02d}")
        t = _read_cpu_temp()
        self._b["cpu"].setText(f"{t:.0f} ℃" if t is not None else "-")
        try:
            free = shutil.disk_usage(".").free / 1e9
            self._b["storage"].setText(f"{free:.1f} GB")
        except OSError:
            self._b["storage"].setText("-")
        self._b["poll"].setText(f"{c.cfg.poll_ms} ms / {c.cfg.retries}")
        lamp = theme.GREEN if c.adam2_connected else theme.RED
        for dot in self._mod_lamps.values():
            dot.setStyleSheet(f"color:{lamp}; font-size:16px;")
        self._b["mA"].setText(f"{c.io.ma(AI.LOADCELL_CURRENT):.2f} mA")
        self._b["vok"].setText("정상" if c.vacuum_ok else "꺼짐")

        allowed, reason = c.vacuum_permission()
        self._perm.setText(
            f"진공 발생(K_VACUUM_ON)\n"
            f"　명령 : {'켜짐' if c.vacuum_command else '꺼짐'}　　"
            f"허가 : {'허용' if allowed else '차단'}\n"
            f"　실제 : {'켜짐' if c.out.vacuum_on else '꺼짐'}　　"
            f"사유 : {reason or '-'}"
        )
        # I/O 그리드는 캐시 기반이라 실패할 여지가 거의 없지만, 만에 하나 실패해도
        # 위 요약(캐시)은 항상 표시되도록 분리한다.
        try:
            self._refresh_io()
        except Exception:
            logging.getLogger("hmi").exception("status I/O 그리드 갱신 실패")

    def _refresh_io(self) -> None:
        # 컨트롤러가 매 스캔 캐시한 값만 사용 — 상태 페이지가 버스를 추가로 폴링하지 않는다
        # (공유 RS-485 노이즈/글리치 최소화).
        io = self.ctrl.io
        if self._tab == 2:
            # 아날로그: 페어 박스. A0~3 전류(mA), A4~7 전압(V = mA_환산 × 0.12).
            self._io_host.hide(); self._ai_host.show()
            ma = io.ma_snapshot()
            for i in range(8):
                if i < 4:
                    self._ai_boxes[i].setText(f"{ma[i]:.2f} mA")
                else:
                    self._ai_boxes[i].setText(f"{ma[i] * 0.12:.3f} V")
            return
        self._ai_host.hide(); self._io_host.show()
        if self._tab == 0:
            di, do, di_ko, do_ko = io.di_snapshot(1), self.a1.cached_do(), _DI1_KO, _DO1_KO
        else:
            di, do, di_ko, do_ko = io.di_snapshot(2), self.a2.cached_do(), _DI2_KO, _DO2_KO
        headers = ["채널", "입력 신호", "상태", "채널", "출력 신호", "상태"]
        rows = []
        states = []
        for i in range(8):
            rows.append([f"DI-{i:02d}", di_ko[i], "켜짐" if di[i] else "꺼짐",
                         f"DO-{i:02d}", do_ko[i], "켜짐" if do[i] else "꺼짐"])
            states.append((di[i], do[i]))
        self._render_grid(headers, rows, states=states)

    def _render_grid(self, headers, rows, states) -> None:
        # 필요한 만큼 위젯 생성/재사용
        ncol = len(headers)
        need = (1 + len(rows)) * ncol
        while len(self._io_rows) < need:
            lab = QLabel("")
            self._io_grid.addWidget(lab, len(self._io_rows) // ncol, len(self._io_rows) % ncol)
            self._io_rows.append(lab)
        # 초과 위젯 숨김
        for idx in range(need, len(self._io_rows)):
            self._io_rows[idx].setText("")
            self._io_rows[idx].hide()
        for idx in range(need):
            self._io_rows[idx].show()
        # 헤더
        for c, h in enumerate(headers):
            w = self._io_rows[c]
            w.setText(h)
            w.setStyleSheet("color:#5b6b7f; font-weight:800; font-size:14px;")
        # 데이터
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                w = self._io_rows[(r + 1) * ncol + c]
                w.setText(str(val))
                color = "#28323f"
                if states is not None and headers[c] == "상태":
                    on = states[r][0] if c < 3 else states[r][1]
                    color = theme.GREEN if on else "#9aa7b4"
                    w.setStyleSheet(f"color:{color}; font-weight:800; font-size:14px;")
                else:
                    w.setStyleSheet(f"color:{color}; font-size:14px;")
        for c in range(ncol):
            self._io_grid.setColumnStretch(c, 1 if headers[c] not in ("채널",) else 0)
