"""HMI 라이트 테마 (목업 v0.4) — 앱 전역 QSS + 색상 상수 + 배지/도트 헬퍼.

v0.3 다크 → v0.4 라이트로 전면 교체. 밝은 회색 배경 + 흰색 카드 + 진한 남색
텍스트. 동적으로 색이 바뀌는 요소(상태 dot, badge, 하중 숫자)는 코드에서
인라인으로 지정하고, 정적 골격/카드/버튼/스탯박스만 이 QSS 로 처리한다.
"""

# --- 팔레트 (v0.4 light) ---------------------------------------------------
BG = "#e9edf2"          # 페이지 배경
PANEL = "#ffffff"       # 카드
PANEL2 = "#f2f5f8"      # 스탯 박스 / 보조 면
LINE = "#d7dfe8"        # 테두리
TEXT = "#1f2a37"        # 기본 텍스트(진한 남색)
TITLE = "#1b2735"       # 제목
MUTED = "#7a8896"       # 라벨/보조 텍스트
GREEN = "#1f9d57"       # 정상
YELLOW = "#e0a020"      # 경고/주의
RED = "#c0392b"         # 위험/정지
BLUE = "#2f6fed"        # 이동/선택
OFF = "#9aa7b4"         # 비활성 도트

QSS = f"""
* {{
    color: {TEXT};
    font-family: 'NanumGothic', 'Noto Sans KR', 'Malgun Gothic', sans-serif;
    font-size: 16px;
}}
QWidget#root {{ background: {BG}; }}
QWidget#topbar {{ background: #ffffff; border-bottom: 1px solid {LINE}; }}
QWidget#statusStrip {{ background: {BG}; border-bottom: 1px solid {LINE}; }}
QWidget#bottomNav {{ background: #ffffff; border-top: 1px solid {LINE}; }}
QStackedWidget {{ background: {BG}; }}

QLabel#brand {{ font-size: 24px; font-weight: 800; color: {TITLE}; }}
QLabel#clock {{ color: #55647a; font-weight: 700; font-size: 16px; }}
QLabel#pageTitle {{ font-size: 22px; font-weight: 800; color: {TITLE}; }}

QFrame#card {{
    background: {PANEL};
    border: 1px solid {LINE};
    border-radius: 12px;
}}
QFrame#pill {{
    background: #ffffff;
    border: 1px solid {LINE};
    border-radius: 10px;
}}
QFrame#stat {{
    background: {PANEL2};
    border: 1px solid #e4eaf1;
    border-radius: 9px;
}}
QLabel#cardTitle {{ color: #5b6b7f; font-weight: 800; font-size: 16px; }}
QLabel#mini {{ color: {MUTED}; font-size: 14px; }}
QLabel#statLabel {{ color: {MUTED}; font-size: 14px; }}
QLabel#statValue {{ color: {TITLE}; font-weight: 800; font-size: 19px; }}

QPushButton {{
    background: #f3f6f9;
    border: 1px solid #cfd8e2;
    border-radius: 9px;
    padding: 9px 10px;
    font-weight: 800;
    color: #2c3a4b;
}}
QPushButton:hover {{ background: #e9eef4; }}
QPushButton:disabled {{ color: #a9b6c2; background: #f1f4f7; border-color: #e2e8ee; }}

QPushButton#primary {{ background: #e2f2e9; border: 1px solid #4dbb84; color: #10864a; }}
QPushButton#primary:hover {{ background: #d3ecdf; }}
QPushButton#danger {{ background: {RED}; border: 1px solid #a93226; color: #ffffff; }}
QPushButton#danger:hover {{ background: #b03325; }}
QPushButton#danger:disabled {{ background: #e7c9c5; border-color: #e0b7b2; color: #f6e7e5; }}

QPushButton#navBtn {{
    background: #f4f7fa; border: 1px solid #d3dce6;
    color: #3a4a5c; border-radius: 10px; font-size: 25px; font-weight: 800;
}}
QPushButton#navBtn:checked {{ background: #1f6fb2; border-color: #195f9c; color: #ffffff; }}

QPushButton#tab {{
    background: #eef2f7; border: 1px solid #d3dce6;
    color: #3a4a5c; border-radius: 8px; font-weight: 800; padding: 7px 14px;
}}
QPushButton#tab:checked {{ background: #2f6fed; border-color: #2a63d4; color: #ffffff; }}

QProgressBar {{
    background: #e6ebf1; border: 1px solid #d4dde7; border-radius: 9px;
    height: 18px; text-align: center; color: #33414f; font-weight: 800; font-size: 12px;
}}
QProgressBar::chunk {{ background: {GREEN}; border-radius: 8px; }}

QTableWidget, QHeaderView::section, QListWidget {{
    background: #ffffff; color: {TEXT}; border: none;
}}
QHeaderView::section {{
    background: #eef2f7; color: #5b6b7f; font-weight: 800;
    padding: 6px; border: none; border-bottom: 1px solid {LINE};
}}
"""


# --- 배지 (상단바 모드/상태) ------------------------------------------------
def badge_qss(variant: str) -> str:
    """상단바 badge (모드/상태) 색상 — v0.4 light.

    outline 계열(자동/수동)은 흰 배경 + 색 테두리, fill 계열(운전/정지 등)은
    옅은 색 배경 + 진한 색 텍스트.
    """
    styles = {
        # 모드 (outline)
        "auto":    ("#ffffff", "#6ea8fe", "#2f6fed"),
        "manual":  ("#ffffff", "#e6b450", "#b9791a"),
        # 상태 (fill, 옅은 배경)
        "running": ("#dff3e6", "#3fae6f", "#12864a"),
        "idle":    ("#eef2f7", "#d3dce6", "#5b6b7f"),
        "stop":    ("#fbe3e3", "#e0a3a0", "#b1291f"),
    }
    bg, border, fg = styles.get(variant, styles["idle"])
    return (f"background:{bg}; border:1px solid {border}; color:{fg};"
            f"border-radius:9px; font-weight:800; font-size:16px; padding:7px 16px;")


def dot_qss(color: str) -> str:
    """상태 스트립의 원형 표시등."""
    return f"background:{color}; border-radius:6px;"
