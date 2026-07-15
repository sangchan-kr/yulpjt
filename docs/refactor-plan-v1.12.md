# v1.12 리팩터링 계획

기준 스펙: `yul_control_system_overview_v1.12.md` (공압 가압 + 진공 흡착 제어)
작성일: 2026-07-15 · 작업 브랜치: `feature/v1.12-refactor`

기존 코드(2026-05, HX711 기반 초기 bring-up, `main` 4커밋)와 하드웨어가 근본적으로
달라져 `hardware/`·`config.py`·`ui/`를 재작성하고 비어있던 `core/`에 상태머신을 추가한다.

---

## 0. 개발 전략 (확정)

- **브랜치**: `feature/v1.12-refactor`에서 작업. `main`은 구버전 복원 앵커로 보존.
- **검증**: 노트북 전용 venv(`py -3.14 -m venv .venv`) + PySide6 6.11, `MOCK_HW=1`,
  **실제 GUI 창**. mock 하드웨어가 가상 신호를 만들고, 시뮬레이터 패널로 입력을
  손으로 토글해 상태머신을 실 하드웨어 없이 끝까지 재현.
- **실 Modbus 드라이버**는 하드웨어 입고 후(Phase D). 지금은 register map을
  `TODO(verify-manual)`로 남기고 mock 경로만 완성.
- **의존성**: v1.12는 Pi GPIO를 전혀 안 씀(HX711 제거, 모든 I/O가 RS-485/아날로그).
  `lgpio`/`rpi-lgpio`/`hx711-multi`/`gpiozero` 전부 제거 → 순수 파이썬 의존성
  (PySide6·pymodbus·pyserial·pyyaml)만 남아 Windows·Pi 동일 requirements.
  PySide6 6.11은 Python 3.14에 설치됨(cp310-abi3 wheel).

## 0.1 결정 사항 (사용자 확정)

1. 브랜치 분리 = 권장대로 `feature/v1.12-refactor`.
2. 데이터 로깅(운전 회수·하중 CSV) = **Phase C**.
3. 진공 흡착 = **자동 시퀀스에서 제외, 수동**. HMI에 진공 토글 버튼 1개를 두고
   버튼 상태에 따라 흡착 유지/해제(blow-off). → Auto 시퀀스는 가압만.
4. AI 읽기 = 센서 4-20mA를 **실제 하중(kgf)으로 환산해 표시**. 로드셀 CSB-1T(1 tf).

---

## 1. 목표 모듈 구조

```
src/control_system/
├── config.py            [재작성]
├── hardware/
│   ├── modbus_hub.py    [신규] pymodbus 시리얼 클라이언트 래퍼(단일 버스 공유)/mock 허브
│   ├── adam4055.py      [신규] 복합 8DI+8DO 모듈 (구 adam_di+adam_relay 대체) — 2 인스턴스
│   ├── adam4017.py      [신규] 8ch 아날로그 입력 (mA 읽기)
│   ├── loadcell.py      [재작성] 4-20mA→kgf 환산 + tare/scale + 캘리브 영속 (HX711/GPIO 제거)
│   ├── signals.py       [신규] 이름 있는 신호 IntEnum(DI1/DO1/DI2/DO2/AI) + IO 파사드
│   ├── adam_di.py       [삭제]
│   └── adam_relay.py    [삭제]
├── core/                              (Phase B)
│   ├── states.py        [신규] State/Alarm enum
│   ├── controller.py    [신규] 스캔 사이클 + 상태머신
│   └── safety.py        [신규] write_actuator_outputs() 단일 출력 초크포인트(§19)
├── ui/                                (Phase C)
│   ├── main_window.py   [재작성] HMI
│   ├── sim_panel.py     [신규, mock 전용] 입력 시뮬레이터 패널
│   └── logging_csv.py   [신규] 운전/하중 CSV 로거
├── main.py              [수정] 허브·모듈·컨트롤러·윈도우 와이어링
└── calibration.yaml                    로드셀 zero_offset/scale 저장
requirements.txt / pyproject.toml       [수정] GPIO/HX711 제거, PySide6 6.11, pymodbus/pyserial/pyyaml
tests/                                   [Phase B/D] 환산·인터록·상태전이 유닛테스트
```

---

## 2. Phase A — 하드웨어 계층 + config

- **ADAM-4055-C = 8DI+8DO 복합 1클래스(`Adam4055`)**. 구 "4055=16DI / 4068=8relay"
  모델 폐기. 인스턴스 2개(unit 1,2)가 하나의 `ModbusHub`(시리얼 버스) 공유.
  - API: `read_di()->list[bool]`(8), `read_do()->list[bool]`(8 리드백),
    `write_do(ch,val)`, `write_do_all(list)`.
- **`Adam4017`**: `read_ma(ch)->float`, `read_all_ma()`. mock은 AI-00에 하중을
  흉내낸 4-20mA 곡선, 나머지 노이즈.
- **`LoadCell`는 드라이버가 아니라 환산기** — Adam4017 AI-00을 소스로:
  ```
  raw_kgf = (mA - 4.0) / 16.0 * full_scale_kgf     # §9, 기본 full_scale_kgf=1000
  load    = (raw_kgf - zero_offset) * scale
  tare(): 현재값으로 zero_offset 설정 → calibration.yaml 저장
  ```
- **`signals.py`**: §18 확정 맵을 IntEnum으로.
  DO1.K_VALVE_DOWN=4, DO1.K_VALVE_UP=5, DI1.SOL_ENABLE_OK=7,
  DI2.VACUUM_OK=0, DO2.K_VACUUM_ON=0, DO2.K_BLOW_OFF_ON=1, AI.LOADCELL_CURRENT=0 …
  `IO` 파사드가 `io.di(DI1.MODE_AUTO)`/`io.set(DO1.K_VALVE_UP,True)`로
  채널↔모듈 매핑을 한 곳에 캡슐화 → 상태머신은 이름만 사용.
  - **입력 반전 맵**: VACUUM_OK(NPN)처럼 반전 가능 신호를 config의 채널별 invert로 처리(§7.2).

**config.py 항목**: `mock_hardware`, `serial_port`(`/dev/ttyUSB0`), `baudrate`, `parity`,
`poll_ms`, `timeout_ms`, `retry`, 노드ID(1/2/3), 로드셀 `ai_channel`/`full_scale_kgf`/
`calibration_path`, 시퀀스 파라미터(`down_dwell_ms`,`up_dwell_ms`,`blowoff_delay_ms`,
`blowoff_hold_ms`,`target_count`,`load_limit_kgf`,`vacuum_timeout_ms`), `input_invert`.

**검증(A)**: 헤드리스(`QT_QPA_PLATFORM=offscreen`) + 스크립트로 신호 이름 read/write,
로드셀 환산·tare 확인.

---

## 3. Phase B — 제어 상태머신 (`core/`)

진공이 수동이 되면서 Auto 시퀀스는 **가압만** 담당(진공 상태는 감시/표시만).

- **State enum**:
  `BOOT, AUTO_IDLE, AUTO_PRECHECK, AUTO_MOVE_DOWN, AUTO_DWELL_DOWN,
   AUTO_MOVE_UP, AUTO_DWELL_UP, AUTO_COUNT_UPDATE, AUTO_COMPLETE,
   MANUAL_IDLE, SAFETY_STOP, ERROR`
- **Alarm enum**(§14): SAFETY_STOP, VALVE_INTERLOCK, MANUAL_CONFLICT,
  DOWN_TIMEOUT, UP_TIMEOUT, VACUUM_FAIL, VACUUM_LOSS, ADAM_COMM_ERROR, LOAD_OVER_LIMIT.
- **`Controller.scan()`**(QTimer 50–100ms): ① 입력 읽기(edge 검출) → ② 상태 평가
  → ③ 원하는 출력 계산 → ④ `write_actuator_outputs()` 단일 초크포인트에서만 실제 출력.
- **안전 규칙(§19)**: `SOL_ENABLE_OK` OFF → 모든 액추에이터 OFF + `SAFETY_STOP` 래치.
  Down/Up 동시 → 차단 + `VALVE_INTERLOCK`. Vacuum/Blow-off 동시 → 차단 + 알람.
  Safety Reset(HMI)로만 래치 해제, 자동 재시작 없음(§8.3).
- **Auto 시퀀스**: IDLE → PRECHECK → MOVE_DOWN(CYL_DOWN_POS 대기, timeout) →
  DWELL_DOWN(하중 감시, LOAD_OVER_LIMIT) → MOVE_UP(CYL_UP_POS 대기, timeout) →
  DWELL_UP → COUNT_UPDATE → 다음 cycle 또는 COMPLETE.
- **Manual**(§11.2): 버튼 눌린 동안만 밸브 ON, 떼면 Closed Center, 동시 누름 → MANUAL_CONFLICT.
- **진공(수동, §3-결정)**: HMI 진공 토글 버튼 상태를 컨트롤러가 읽어
  ON → K_VACUUM_ON=ON / K_BLOW_OFF_ON=OFF, OFF → K_VACUUM_ON=OFF 후
  blowoff_delay → K_BLOW_OFF_ON 펄스(blowoff_hold) → OFF. SOL_ENABLE·인터록 적용.
  VACUUM_OK는 표시용, ON 상태에서 timeout이면 VACUUM_FAIL/유지 중 이탈이면 VACUUM_LOSS 표시.
- **검증(B)**: pytest로 인터록·상태전이(가짜 IO 주입) 단위 테스트.

---

## 4. Phase C — HMI + 시뮬레이터 + 로깅

- **표시**(§10.1): 모드, 상태, 실린더 위치, 현재/최대 하중(kgf), 목표/현재 카운트,
  dwell 시간, 진공상태, SOL_ENABLE, 알람 메시지, 시그널 타워 색(§15).
- **버튼**(§10.2 + 결정3): Safety Reset, Alarm Clear, Count Reset, Load Zero(tare),
  **Vacuum ON/OFF 토글**(흡착 유지/해제), (옵션) Blow-off 수동 펄스.
- **`sim_panel.py`(mock 전용)**: DI(MODE_AUTO/Auto Start·Stop/Manual Up·Down/
  CYL_UP·DOWN/SOL_ENABLE_OK/VACUUM_OK)를 토글해 전체 시퀀스 재현. `MOCK_HW=0`이면 숨김.
- **로깅(결정2)**: cycle 완료 시 타임스탬프·카운트·최대하중·알람을 CSV로 append.
- UI는 컨트롤러 상태를 QTimer로 읽어 그림(출력 직접 구동 금지, 명령 플래그만 전달).
- **검증(C)**: 노트북 실제 창에서 Auto 1사이클 + Safety Stop/Reset + 수동 진공 토글
  + 하중 표시 눈으로 확인.

---

## 5. Phase D — 실 하드웨어 연동 (입고 후)

- `Adam4055`/`Adam4017` 실 Modbus register map 채우기(Advantech 매뉴얼 대조),
  NPN(VACUUM_OK) 입력 반전 확정, `MOCK_HW=0` 시운전, 로드셀 캘리브레이션,
  진공 에너지 세이빙(§13) 적용 여부 결정.

---

## 6. 하드웨어 설정 — 로드셀/앰프 게인 (부록)

**로드셀 CSB-1T**: 정격출력 2.0 mV/V, 용량 1 tf = 1000 kgf, 권장 여기전압 10V.
**앰프 NCT-I420 출력 = 4–20 mA** → 게인표의 `Vout1~5V (Iout4~20mA)` 열 사용.
그 열 값 = 20 mA에 도달하는 입력 span(mV/V).

### 권장 세팅 (만용량 1000 kgf)

DIP SW1 = **OFF · OFF · OFF · ON** (1→4), 내부 Gain 278.
→ 0 kgf = 4 mA, 1000 kgf = 20 mA. 소프트웨어: `load_kgf = (mA-4)/16*1000`.

### 분해능 최적화 (실제 최대 하중이 1t보다 작을 때)

필요 span = `2.0 × (최대하중/1000)` mV/V, 그 이상인 가장 가까운 행 선택.
소프트웨어 `full_scale_kgf`를 그 값으로 맞춤.

| 세 번째 열(mV/V) | DIP(1-2-3-4) | 20 mA = 하중 | Gain |
|:---:|:---:|:---:|:---:|
| 2.0 | OFF OFF OFF ON | 1000 kgf (기본) | 278 |
| 1.0 | OFF ON OFF OFF | 500 kgf | 556 |
| 0.85 | OFF OFF ON ON | 425 kgf | 651 |
| 0.5 | ON OFF OFF OFF | 250 kgf | 1112 |
| 0.4 | ON OFF OFF ON | 200 kgf | 1394 |

> "압력" 표시가 필요하면 하중(kgf)/접촉면적으로 환산(압력=힘/면적). 기본은 하중(kgf) 표시.

---

## 7. 미결/입고 후 확인

- 실제 최대 가압 하중 → 앰프 게인 행 확정(미정 시 1000 kgf 기본).
- ADAM-4055-C / ADAM-4017+ Modbus register map(매뉴얼 대조, Phase D).
- VACUUM_OK NPN 입력 직결 가능 여부/반전(§7.2, Phase D).
- ADAM-4017+ 엔지니어링 단위(mA) vs raw count 읽기 모드(기본 mA).
