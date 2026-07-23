"""부팅 화면 (목업 v0.4 boot.png).

시작 시 통신/모듈 상태를 순차 점검하는 모습을 보여준 뒤 on_done 콜백을 호출한다.
mock 모드에서는 실제 통신 없이 순차적으로 '완료' 표시만 진행한다.
"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget,
)

from . import theme

# (이름, 설명, 완료시 상태문구, 상태색)
_ITEMS = [
    ("제어 프로그램", "라즈베리파이 제어 서비스 실행", "정상", theme.GREEN),
    ("디지털 입출력 모듈 1", "ADAM-4055-C · 실린더 및 조작부", "연결됨", theme.GREEN),
    ("디지털 입출력 모듈 2", "ADAM-4055-C · 진공 제어", "연결됨", theme.GREEN),
    ("하중 입력 모듈", "ADAM-4017+ · 로드셀 입력", "연결됨", theme.GREEN),
    ("액추에이터 구동 허가", "비상정지 및 영역센서 상태 확인", "대기", theme.YELLOW),
]


class BootScreen(QWidget):
    def __init__(self, on_done) -> None:
        super().__init__()
        self._on_done = on_done
        self.setObjectName("root")
        self.setStyleSheet(theme.QSS)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addStretch(1)

        card = QFrame(); card.setObjectName("card")
        card.setMaximumWidth(660)
        cl = QVBoxLayout(card); cl.setContentsMargins(28, 24, 28, 24); cl.setSpacing(10)

        title = QLabel("반복 가압 측정기")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"font-size:30px; font-weight:900; color:{theme.TITLE};")
        sub = QLabel("시스템 시작 및 통신 상태 확인")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setObjectName("mini")
        cl.addWidget(title)
        cl.addWidget(sub)
        cl.addSpacing(6)

        self._rows = []
        for name, desc, _st, _c in _ITEMS:
            row = QFrame(); row.setObjectName("stat")
            rl = QHBoxLayout(row); rl.setContentsMargins(12, 9, 14, 9); rl.setSpacing(12)
            mark = QLabel("○"); mark.setFixedWidth(22)
            mark.setStyleSheet(f"color:{theme.OFF}; font-size:18px; font-weight:900;")
            box = QVBoxLayout(); box.setSpacing(1)
            nm = QLabel(name); nm.setStyleSheet(f"font-weight:800; color:{theme.TITLE};")
            ds = QLabel(desc); ds.setObjectName("mini")
            box.addWidget(nm); box.addWidget(ds)
            status = QLabel("확인 중"); status.setStyleSheet(f"color:{theme.MUTED}; font-weight:800;")
            rl.addWidget(mark)
            rl.addLayout(box, 1)
            rl.addWidget(status)
            cl.addWidget(row)
            self._rows.append((mark, status))

        self._bar = QProgressBar(); self._bar.setRange(0, len(_ITEMS)); self._bar.setValue(0)
        self._bar.setTextVisible(False); self._bar.setFixedHeight(10)
        self._bar.setStyleSheet(
            "QProgressBar{background:#e6ebf1;border:1px solid #d4dde7;border-radius:6px;}"
            "QProgressBar::chunk{border-radius:6px;"
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #2f6fed,stop:1 #22a35a);}"
        )
        cl.addSpacing(4)
        cl.addWidget(self._bar)

        center = QHBoxLayout()
        center.addStretch(1); center.addWidget(card); center.addStretch(1)
        outer.addLayout(center)
        outer.addStretch(1)

        self._i = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step)
        self._timer.start(450)

    def _step(self) -> None:
        if self._i < len(self._rows):
            mark, status = self._rows[self._i]
            _n, _d, st, color = _ITEMS[self._i]
            mark.setText("✓")
            mark.setStyleSheet(f"color:{color}; font-size:18px; font-weight:900;")
            status.setText(st)
            status.setStyleSheet(f"color:{color}; font-weight:800;")
            self._i += 1
            self._bar.setValue(self._i)
            return
        self._timer.stop()
        QTimer.singleShot(500, self._finish)

    def _finish(self) -> None:
        if self._on_done:
            self._on_done()
