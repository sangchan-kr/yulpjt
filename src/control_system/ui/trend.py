"""하중 실시간 트렌드 (외부 라이브러리 없이 QPainter 로 그림)."""

from collections import deque

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from . import theme


class LoadTrend:
    """하중 샘플 링버퍼. main_window 가 매 스캔 append 한다."""

    def __init__(self, maxlen: int = 300) -> None:
        self._buf: deque[float] = deque(maxlen=maxlen)

    def add(self, v: float) -> None:
        self._buf.append(v)

    def samples(self) -> list[float]:
        return list(self._buf)


class TrendWidget(QWidget):
    def __init__(self, trend: LoadTrend, limit_getter=None) -> None:
        super().__init__()
        self._trend = trend
        self._limit_getter = limit_getter     # 하중 상한선 표시용 콜백
        self.setMinimumHeight(90)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        # v0.4 light: 흰 패널 + 옅은 테두리/그리드
        p.fillRect(self.rect(), QColor("#ffffff"))
        p.setPen(QPen(QColor("#e2e8f0"), 1))
        p.drawRect(0, 0, w - 1, h - 1)
        p.setPen(QPen(QColor("#eef2f7"), 1))
        for i in range(1, 4):
            gy = int(h * i / 4)
            p.drawLine(0, gy, w, gy)

        data = self._trend.samples()
        limit = self._limit_getter() if self._limit_getter else 0
        top = max([limit] + data + [1.0]) * 1.1     # y 스케일 (여유 10%)

        # 상한선
        if limit and top:
            y = h - (limit / top) * h
            p.setPen(QPen(QColor(theme.RED), 1, Qt.PenStyle.DashLine))
            p.drawLine(0, int(y), w, int(y))

        if len(data) >= 2:
            p.setPen(QPen(QColor(theme.BLUE), 2))
            n = len(data)
            step = w / (n - 1)
            prev = None
            for i, v in enumerate(data):
                x = i * step
                y = h - (v / top) * h if top else h
                if prev is not None:
                    p.drawLine(int(prev[0]), int(prev[1]), int(x), int(y))
                prev = (x, y)
        p.end()
