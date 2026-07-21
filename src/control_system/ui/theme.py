"""HMI 다크 테마 (목업 v0.3 팔레트) — 앱 전역 QSS + 색상 상수.

동적으로 색이 바뀌는 요소(상태 dot, badge, 하중 숫자)는 코드에서 인라인으로
색을 지정하고, 정적 골격/카드/버튼만 이 QSS 로 처리한다.
"""

BG = "#0b1220"
PANEL = "#111b2d"
PANEL2 = "#172338"
LINE = "#2a3a52"
TEXT = "#eef4fb"
MUTED = "#93a4b8"
GREEN = "#22c55e"
YELLOW = "#f5b93f"
RED = "#ef4444"
BLUE = "#38bdf8"
OFF = "#596579"

QSS = f"""
* {{
    color: {TEXT};
    font-family: 'Malgun Gothic', 'Noto Sans KR', sans-serif;
    font-size: 13px;
}}
QWidget#root {{ background: {BG}; }}
QWidget#topbar {{ background: #0f1828; border-bottom: 1px solid {LINE}; }}
QWidget#statusStrip {{ background: {PANEL}; border-bottom: 1px solid {LINE}; }}
QWidget#bottomNav {{ background: #0f1828; border-top: 1px solid {LINE}; }}
QStackedWidget {{ background: {BG}; }}

QLabel#brand {{ font-size: 20px; font-weight: 800; }}
QLabel#clock {{ color: #b7c4d4; font-weight: 700; }}

QFrame#card {{
    background: {PANEL};
    border: 1px solid {LINE};
    border-radius: 10px;
}}
QLabel#cardTitle {{ color: #9fb0c5; font-weight: 800; }}
QLabel#mini {{ color: #91a4bb; }}

QPushButton {{
    background: #1a2a40;
    border: 1px solid #3a4c65;
    border-radius: 8px;
    padding: 8px 6px;
    font-weight: 800;
    color: {TEXT};
}}
QPushButton:hover {{ background: #223452; }}
QPushButton:disabled {{ color: #566274; background: #141f30; border-color: #263346; }}
QPushButton#danger {{ background: #4c1d21; border-color: #9e2f38; color: #ffd6d9; }}

QPushButton#navBtn {{
    background: #172338; border: 1px solid {LINE};
    color: #b9c7d8; border-radius: 8px; font-size: 14px;
}}
QPushButton#navBtn:checked {{ background: #0c4a6e; border-color: {BLUE}; color: #e9fbff; }}

QProgressBar {{
    background: #223048; border: 1px solid #31435f; border-radius: 8px;
    height: 16px; text-align: center; color: {TEXT}; font-weight: 800; font-size: 11px;
}}
QProgressBar::chunk {{ background: {BLUE}; border-radius: 7px; }}
"""


def badge_qss(variant: str) -> str:
    """상단바 badge (모드/상태) 색상."""
    styles = {
        "auto": ("#0d3b55", "#0e7490", "#bff5ff"),
        "manual": ("#4a3311", "#a16207", "#ffe8a3"),
        "running": ("#0e3b23", "#168a46", "#a7f3c2"),
        "idle": ("#2a3445", "#3a4660", "#d8e0ea"),
        "stop": ("#541c20", "#b4232b", "#ffc8cc"),
    }
    bg, border, fg = styles.get(variant, styles["idle"])
    return (f"background:{bg}; border:1px solid {border}; color:{fg};"
            f"border-radius:7px; font-weight:800; padding:4px 10px;")


def dot_qss(color: str) -> str:
    """상태 스트립의 원형 표시등."""
    return f"background:{color}; border-radius:6px;"
