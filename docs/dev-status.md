# 개발 현황 & 재개 가이드 (v1.12)

최종 갱신: 2026-07-15 · 브랜치: `feature/v1.12-refactor`

노트북에서 나중에 이어서 개발할 때 이 문서부터 보면 된다.
(왜/무엇을 바꿨는지는 [refactor-plan-v1.12.md](refactor-plan-v1.12.md) 참고)

---

## 0. 다른 기기의 Claude Code 에서 이어가기

Claude Code 대화 자체는 기기 로컬(`~/.claude`)에만 저장되며 다른 노트북으로
자동 동기화되지 않는다. **이전 채팅 세션을 그대로 옮길 수는 없다.** 대신 이
repo(특히 이 문서)를 "단일 진실 소스"로 삼아 새 대화에서 맥락을 복원한다.

다른 노트북에서:

1. `git clone https://github.com/sangchan-kr/yulpjt.git && cd yulpjt`
2. `git checkout feature/v1.12-refactor`
3. 그 폴더에서 Claude Code 를 열고 이렇게 시작한다:
   > "yulpjt v1.12 이어서 개발하자. `docs/dev-status.md` 랑 `docs/refactor-plan-v1.12.md` 읽고 현황 파악해줘."
4. 아래 3절대로 venv 만들고 테스트가 그린인지 확인한 뒤 5절(Phase D)로 진행.

참고: 개인 메모리(`~/.claude/.../memory`)는 이 repo 에 없다(기기 로컬 + 타
프로젝트 정보 포함). 그래서 재개에 필요한 모든 사실을 이 문서에 담아 둔다.

---

## 1. 지금까지 한 것 (Phase A → B → C 완료, mock 검증)

| 단계 | 커밋 | 내용 |
|---|---|---|
| A | `45c7614` | 하드웨어 계층 + config 재작성 |
| B | `bb06da1` | `core/` 제어 상태머신 |
| C | `61c7d05` | HMI 단일화면 + 컨트롤러 연동 + 시뮬레이터 + CSV |
| C2 | `0a322fc` | 진공 완전 분리(논블로킹 경고), timeout/peak 분리, HMI 설계 문서 |
| C3 | (이번) | HMI 셸 재작성: 다크 테마 + 상단바/상태스트립/하단네비/페이지스택 + 메인페이지(목업 v0.3) + Safety 오버레이 |

기존 2026-05 초기 bring-up(HX711 기반)은 `main` 브랜치에 그대로 보존.
v1.12 재구성은 전부 이 feature 브랜치에 있고 **mock 으로만 검증됨(실 하드웨어 미연결)**.
HMI 단계 정의는 [hmi-design.md](hmi-design.md) 참고. 남은 HMI: C4(조건설정/시스템상태/로그/도움말 실제화), C5(유지보수/트렌드/권한/CSV export).

## 2. 코드 지도

```
src/control_system/
├── config.py              설정 + 환경변수 오버라이드 + 앰프 게인 help
├── main.py                조립: 허브→ADAM→IO→로드셀→Controller→HMI
├── hardware/
│   ├── signals.py         이름 있는 신호(DI1/DO1/DI2/DO2/AI) + IO 파사드(stage/flush)
│   ├── modbus_hub.py      RS-485 버스 pymodbus 래퍼 / mock
│   ├── adam4055.py        복합 8DI+8DO 모듈 (×2)
│   ├── adam4017.py        8ch 아날로그 입력 (4-20mA)
│   └── loadcell.py        4-20mA→kgf 환산 + tare/scale + calibration.json
├── core/
│   ├── states.py          State(12) / Alarm(9) / Outputs
│   ├── safety.py          apply_output_safety() 단일 출력 초크포인트(§19)
│   └── controller.py      scan() 상태머신 (Auto/Manual/Safety/수동진공/알람/타워)
└── ui/
    ├── main_window.py     HMI (타워·하중·상태·카운트·진공·알람 + 조작 버튼)
    ├── sim_panel.py       mock 입력 시뮬레이터 (체크박스/순간버튼/하중슬라이더)
    └── logging_csv.py     사이클당 CSV 로깅
tests/
├── test_hardware_smoke.py  하드웨어 계층 6종
└── test_controller.py      상태머신 15종
```

## 3. 재개 방법 (새 노트북/클린 체크아웃)

```powershell
git clone https://github.com/sangchan-kr/yulpjt.git
cd yulpjt
git checkout feature/v1.12-refactor
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
$env:MOCK_HW="1"; .\.venv\Scripts\python.exe -m control_system
```

테스트: `.\.venv\Scripts\python.exe tests\test_hardware_smoke.py` / `tests\test_controller.py`

## 4. 확정된 설계 결정

1. 브랜치: `feature/v1.12-refactor` (main 보존)
2. 데이터 로깅: 사이클당 CSV (`data/run_log.csv`, gitignore)
3. **진공은 자동 시퀀스에서 제외 → HMI "진공 흡착" 토글 버튼으로 수동 제어**
4. 로드셀: CSB-1T 1t, 최대 가압 **1000 kgf 유지**.
   앰프 NCT-I420 **DIP SW1 = OFF·OFF·OFF·ON (Gain 278)**, 4mA=0 / 20mA=1000kgf,
   `loadcell_full_scale_kgf=1000`. (범위 변경 시 config.py 의 AMP_GAIN_HELP 표 참고)

## 5. 다음 방향 — Phase D (실 하드웨어 입고 후)

우선순위 순:

1. **실 Modbus 드라이버 채우기** — `adam4055.py`/`adam4017.py` 의
   `_DI_ADDR`/`_DO_ADDR`/`_AI_ADDR` 등 register map 을 Advantech 매뉴얼로 확인.
   지금은 `TODO(verify-manual)` 로 표시된 자리표시자.
2. **ADAM-4017+ 읽기 모드 확정** — 엔지니어링 단위(mA) vs raw count. 현재 raw→mA
   환산이 자리표시자(`_RAW_FULL`). 실제 스케일 확인.
3. **VACUUM_OK NPN 입력** — 배선 검증 후 논리 반전 필요 여부 결정.
   필요하면 `config.invert_vacuum_ok=True` (IO 파사드가 이미 반전 지원).
4. **`MOCK_HW=0` 시운전** — 통신 타임아웃/재시도(`ADAM_COMM_ERROR` 경로) 실측 튜닝,
   `poll_ms`/`timeout_ms` 조정.
5. **로드셀 캘리브레이션** — 실하중 대비 `zero_offset`/`scale` 확정 (Load Zero + 기준분동).
6. **Pi 배포** — deploy/ 스크립트(systemd/labwc) 점검, 풀스크린 키오스크 확인.

## 6. 미해결/검토 항목

- `ADAM_COMM_ERROR` 알람은 정의만 있고 실 통신 예외 연결은 Phase D 에서 (mock 은 예외 없음).
- Auto Stop 은 현재 즉시 중단(IDLE). 스펙의 pause/resume 세분화는 필요 시 추가.
- 진공 에너지 세이빙(§13)은 단순 유지 방식만 구현. 시운전 후 적용 여부 결정.
- '압력(MPa/bar)' 표시가 필요하면 접촉 면적 입력 → kgf 환산 추가.
