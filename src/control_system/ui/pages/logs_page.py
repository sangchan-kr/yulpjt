"""로그 페이지 (목업 v0.3 / handoff §12).

탭: 운전 기록(사이클 CSV) · 알람 · 이벤트(메모리 이벤트 로그) · 하중 트렌드(C5).
알람과 이벤트를 분리해, 상태전환 등 이벤트에 묻히지 않고 알람만 확인할 수 있게 한다.

USB 저장: 꽂힌 USB 메모리에 운전기록(CSV)과 시스템로그(app.log)를 타임스탬프
파일명으로 복사한다. (sudo 불필요 — RPi 데스크톱이 /media/<user>/ 로 자동 마운트)
"""

import datetime
import logging
import os
import shutil

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

# 이벤트 코드 분류: 알람 탭(문제/경고/안전정지/오류) vs 이벤트 탭(상태전환·조작).
_ALARM_CODES = {"ALARM", "VACUUM_WARN", "SAFETY", "ERROR"}
_EVENT_CODES = {"STATE", "VACUUM_COMMAND"}
_CODE_KO = {"ALARM": "알람", "VACUUM_WARN": "진공경고", "SAFETY": "안전정지",
            "ERROR": "오류정지", "STATE": "상태전환", "VACUUM_COMMAND": "진공명령"}

# 알람 코드값 → 한글 상세 표기.
_ALARM_KO = {
    "VALVE_INTERLOCK": "밸브 인터록(상승/하강 동시 명령)",
    "MANUAL_CONFLICT": "수동 상승/하강 동시 입력",
    "DOWN_TIMEOUT": "하강 위치 미도달",
    "UP_TIMEOUT": "상승 위치 미도달",
    "LOAD_OVER_LIMIT": "하중 상한 초과",
    "ADAM_COMM_ERROR": "통신 오류(USB/RS-485)",
    "VACUUM_NOT_REACHED": "진공 미도달",
    "VACUUM_SIGNAL_ABNORMAL": "진공 신호 이상",
    "VACUUM_BLOWOFF_INTERLOCK": "진공/파기 동시",
}

# 본문: 등폭 느낌으로 열을 맞추고, 화면 폭에 들어오도록 글자 크기를 줄인다.
_BODY_QSS = ("font-family:'DejaVu Sans Mono','D2Coding','Nanum Gothic Coding',monospace;"
             "font-size:13px; color:#28323f;")


def _find_usb_mount() -> str | None:
    """꽂힌 USB 저장소의 쓰기 가능한 마운트 경로를 찾는다(없으면 None).

    SD 카드는 /dev/mmcblk* 이고 USB 메모리는 /dev/sd* 이므로 /dev/sd* 마운트만 고른다.
    데스크톱(udisks)이 /media/<user>/<라벨> 로 자동 마운트한다.
    """
    try:
        with open("/proc/mounts", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return None
    for line in lines:
        parts = line.split()
        if len(parts) < 2 or not parts[0].startswith("/dev/sd"):
            continue
        mnt = parts[1].replace("\\040", " ")            # /proc/mounts 는 공백을 \040 로
        if not (mnt.startswith("/media/") or mnt.startswith("/run/media/")
                or mnt.startswith("/mnt/")):
            continue
        if os.path.isdir(mnt) and os.access(mnt, os.W_OK):
            return mnt
    return None


class LogsPage(QWidget):
    def __init__(self, run_log_path: str, event_log) -> None:
        super().__init__()
        self.run_log_path = run_log_path
        self.event_log = event_log
        self._tab = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10); root.setSpacing(6)

        tabs = QHBoxLayout()
        self._group = QButtonGroup(self); self._group.setExclusive(True)
        for i, name in enumerate(("운전 기록", "알람", "이벤트", "하중 트렌드")):
            b = QPushButton(name); b.setObjectName("tab"); b.setCheckable(True)
            b.clicked.connect(lambda _=False, idx=i: self._set_tab(idx))
            self._group.addButton(b, i)
            tabs.addWidget(b)
        self._group.button(0).setChecked(True)
        tabs.addStretch(1)
        # USB 저장 버튼 (우측 끝)
        self._b_usb = QPushButton("USB 저장")
        self._b_usb.setObjectName("primary")
        self._b_usb.setMinimumHeight(38)
        self._b_usb.setMinimumWidth(110)
        self._b_usb.clicked.connect(self._download_usb)
        tabs.addWidget(self._b_usb)
        root.addLayout(tabs)

        self._status = QLabel("")
        self._status.setStyleSheet("color:#5b6b7f; font-size:12px; font-weight:700;")
        self._status.setWordWrap(True)
        root.addWidget(self._status)

        card = QFrame(); card.setObjectName("card")
        cl = QVBoxLayout(card)
        self._body = QLabel("")
        self._body.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._body.setStyleSheet(_BODY_QSS)
        # 긴 로그(최대 60줄·긴 줄)가 창을 밀어 하단 네비가 커지/안 줄어드는 문제 방지:
        # 본문을 스크롤 영역에 담아 페이지 크기를 카드 안으로 가둔다(초과분은 스크롤).
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:transparent;} QLabel{background:transparent;}")
        scroll.setWidget(self._body)
        cl.addWidget(scroll, 1)
        root.addWidget(card, 1)

    def _set_tab(self, idx: int) -> None:
        self._tab = idx
        self.update_view()

    def update_view(self) -> None:
        if self._tab == 0:
            self._body.setText(self._run_log_text())
        elif self._tab == 1:
            self._body.setText(self._event_text(_ALARM_CODES, "알람 없음."))
        elif self._tab == 2:
            self._body.setText(self._event_text(_EVENT_CODES, "이벤트 없음."))
        else:
            self._body.setText("하중 실시간 트렌드는 C5 에서 제공됩니다.")

    @staticmethod
    def _short_ts(ts: str) -> str:
        """'2026-10-15T03:48:32' → '10-15 03:48:32' (연도 제거, T→공백)."""
        ts = ts.replace("T", " ")
        return ts[5:] if len(ts) >= 16 and ts[4] == "-" else ts

    def _run_log_text(self) -> str:
        if not os.path.exists(self.run_log_path):
            return "운전 기록 없음."
        try:
            with open(self.run_log_path, encoding="utf-8") as f:
                rows = f.read().strip().splitlines()
        except OSError:
            return "운전 기록을 읽을 수 없음."
        header, *data = rows
        lines = ["시각            카운트   최대하중  알람"]
        for row in data[-30:][::-1]:
            parts = row.split(",")
            while len(parts) < 4:
                parts.append("")
            ts, cnt, load, alarms = parts[:4]
            lines.append(f"{self._short_ts(ts):<14} {cnt:>5}  {load:>8}  {alarms}")
        return "\n".join(lines) if data else "운전 기록 없음."

    def _event_text(self, codes, empty: str) -> str:
        items = self.event_log.recent(60, codes=codes)
        if not items:
            return empty
        lines = ["시각       종류       상세"]
        for ts, code, detail in items:
            lines.append(f"{ts:<8} {_CODE_KO.get(code, code):<8} {_ALARM_KO.get(detail, detail)}")
        return "\n".join(lines)

    # ------------------------------------------------------------ USB 다운로드
    def _download_usb(self) -> None:
        """꽂힌 USB 메모리에 운전기록·시스템로그를 타임스탬프 파일명으로 저장."""
        usb = _find_usb_mount()
        if usb is None:
            self._status.setText("USB 저장: 드라이브를 찾을 수 없습니다. USB 메모리를 꽂은 뒤 다시 누르세요.")
            self._status.setStyleSheet("color:#b1291f; font-size:12px; font-weight:700;")
            return
        # 시스템 로그(app.log)는 RAM 버퍼에 모였다 저장되므로, 복사 전에 flush.
        for h in logging.getLogger().handlers:
            try:
                h.flush()
            except Exception:  # noqa: BLE001
                pass
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        data_dir = os.path.dirname(self.run_log_path) or "."
        jobs = [
            (self.run_log_path, f"운전기록_{ts}.csv"),
            (os.path.join(data_dir, "app.log"), f"시스템로그_{ts}.log"),
        ]
        saved, errs = [], []
        for src, name in jobs:
            if not os.path.exists(src):
                continue
            try:
                shutil.copyfile(src, os.path.join(usb, name))
                saved.append(name)
            except OSError as e:
                errs.append(f"{name}: {e}")
        try:
            os.sync()                       # USB 로 실제 기록 완료(뽑아도 안전)
        except Exception:  # noqa: BLE001
            pass
        if saved and not errs:
            self._status.setText(f"USB 저장 완료 → {usb}  (파일: {', '.join(saved)})")
            self._status.setStyleSheet("color:#10864a; font-size:12px; font-weight:700;")
        elif saved:
            self._status.setText(f"일부 저장({', '.join(saved)}). 오류: {'; '.join(errs)}")
            self._status.setStyleSheet("color:#8a5a12; font-size:12px; font-weight:700;")
        else:
            msg = "; ".join(errs) if errs else "저장할 로그 파일이 없습니다."
            self._status.setText(f"USB 저장 실패: {msg}")
            self._status.setStyleSheet("color:#b1291f; font-size:12px; font-weight:700;")
