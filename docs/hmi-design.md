# HMI 디자인 초안 (PySide6)

기준 목업: [hmi-mockup-v0.3.html](hmi-mockup-v0.3.html) · 사양: [hmi-handoff-v0.2.md](hmi-handoff-v0.2.md)
대상: Waveshare 7" 1024×600 터치 · 다크 테마

이 문서는 목업(v0.3)을 PySide6 로 옮기기 위한 구조/테마/단계 정의다.
현재 코드의 Phase C 단일 화면 HMI 를 이 구조로 재작성한다(C3~C5).

---

## 1. 화면 골격

```
QMainWindow
└─ central QWidget (QVBoxLayout)
   ├─ TopBar        (제목 | AUTO/MANUAL | 상태 badge | 시각 | ⚙설정)
   ├─ StatusStrip   (SOL · CYLINDER · VACUUM · LOADCELL · ADAM  — dot+텍스트)
   ├─ QStackedWidget (페이지 전환)
   │   ├─ MainPage        운전 (기본)
   │   ├─ SettingsPage    조건설정
   │   ├─ StatusPage      시스템상태
   │   ├─ LogsPage        로그
   │   ├─ HelpPage        도움말
   │   └─ MaintenancePage 유지보수 (관리자, ⚙에서 진입)
   └─ BottomNav     [운전][조건설정][시스템상태][로그][도움말]

SafetyStop 은 페이지가 아니라 MainWindow 위에 뜨는 모달 오버레이(QDialog/overlay widget).
```

TopBar/StatusStrip/BottomNav 는 모든 페이지 공통(스택 밖에 고정).

## 2. 테마 (목업 팔레트 → Qt QSS)

앱 전역 QSS 하나로 관리 (`ui/theme.py` 의 상수 문자열).

```
배경        #0b1220      패널 #111b2d / #172338      경계선 #2a3a52
텍스트      #eef4fb      약한 텍스트 #93a4b8
green #22c55e  yellow #f5b93f  red #ef4444  blue #38bdf8  off #596579
카드 radius 10px, 버튼 radius 8px, 상태 dot 원형 10px + glow
폰트: Noto Sans KR / Malgun Gothic (Windows 기본)
```

상태 dot 은 `QLabel` 에 `border-radius` + 배경색, on 시 색상 클래스 부여
(`setProperty("state","green")` + QSS 셀렉터).

## 3. 페이지 ↔ 컨트롤러 데이터 매핑

| 페이지 | 표시/조작 | 컨트롤러 소스 |
|---|---|---|
| StatusStrip | SOL/CYL/VACUUM/LOADCELL/ADAM | `sol_enable_ok`, CYL DI, `vacuum_command`+`vacuum_ok`, 로드셀 유효성, `adam2_connected` |
| Main·공정 | 상태/step/남은 dwell/실린더 | `state`, dwell 남은시간, CYL DI |
| Main·하중 | 현재/사이클최대/운전최대/상한 | `load_kgf`, `cycle_peak_load_kgf`, `run_peak_load_kgf`, `load_limit` |
| Main·카운트 | 현재/목표/진행% | `count`, `target_count` |
| Main·진공 | Command/OK/토글 | `vacuum_command`, `vacuum_ok`, `set_vacuum()`, 허용조건/사유 |
| Main·조작 | Safety Reset/Alarm Clear/Count Reset/Load Zero | `cmd_*()` |
| Settings | 카운트·dwell·timeout·상한·vacuum timeout·저장 | 런타임 설정모델(영속) |
| Status | CPU/저장/uptime·노드통신·프로세스·DO Command/Permission/Actual | 시스템 + 컨트롤러 |
| Logs | 운전/알람/진공이벤트/트렌드 | CSV + 이벤트 로그 |
| Maintenance | 진공/blow-off hold-to-run, DI/DO 시험, 교정 | 컨트롤러 유지보수 API |

## 4. 진공 표시 규칙 (완전 분리 원칙)

- 진공 Command 와 VACUUM_OK 를 **항상 별도 표시**.
- 진공 상태 4종: OFF / BUILDING(cmd ON, OK OFF) / OK / RESIDUAL(cmd OFF, OK ON).
- **진공 경고(VACUUM_NOT_REACHED·SIGNAL_ABNORMAL·BLOWOFF_INTERLOCK)는 논블로킹**:
  자동운전을 막지 않고, 시그널 타워 Red/기계 상태에 영향 주지 않는다.
  메인 화면 진공 영역에만 경고로 표시한다.
- Blow-off 버튼은 메인 화면에 없음 → 유지보수 페이지 hold-to-run 만.

## 5. 구현 단계

- **C2 (지금)**: UI 전에 컨트롤러 로직을 사양에 맞춘다 — 진공 완전 분리(논블로킹
  경고, 자동 blow-off 제거), Safety Stop 진공 래치 OFF, 진공 ON 허용조건 +
  ADAM#2 통신 게이팅, 하강/상승 timeout 분리, cycle/run peak 하중 분리.
- **C3**: 골격(TopBar/StatusStrip/BottomNav/QStackedWidget) + 테마 QSS +
  MainPage 를 목업대로 + 진공 토글(허용조건/사유). SafetyStop 오버레이.
- **C4**: SettingsPage(런타임+영속), StatusPage, LogsPage, HelpPage.
- **C5 (2차)**: MaintenancePage(진공/blow-off hold-to-run, DO 시험, 교정),
  하중 실시간 트렌드, 권한, CSV export.

## 6. 유지 원칙

- 물리 버튼(Auto Start/Stop, Manual Up/Down, Auto/Manual, Main Power)은 HMI 에
  중복 구현하지 않는다. mock 시뮬레이터(sim_panel)에서만 흉내낸다.
- HMI 는 컨트롤러에 명령 플래그만 전달, 출력은 컨트롤러 단일 초크포인트에서만.
- 명령값과 실제 출력값을 구분해 표시(특히 진공).
