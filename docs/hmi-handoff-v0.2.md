# 반복 가압 측정기 HMI 개발 전달사항 v0.2

- 작성 목적: Raspberry Pi 기반 HMI/제어 프로그램 개발 전달용
- 적용 장비: 반복 가압 측정기
- 표시장치: Waveshare 7-inch HDMI Touch LCD
- 컨트롤러: Raspberry Pi 5
- 외부 I/O: ADAM-4055-C × 2, ADAM-4017+-F × 1
- 통신: Modbus RTU over ADAM-4561-CE
- 기준 변경사항: **진공은 자동 시퀀스에 포함하지 않고 작업자가 HMI 메인 화면에서 수동 ON/OFF한다.**

---

## 1. 개발 범위

HMI는 다음 기능을 제공한다.

1. 장비 운전 상태 표시
2. 반복 가압 조건 설정
3. 현재 하중 및 사이클 결과 표시
4. 진공 수동 ON/OFF
5. Safety Stop 및 일반 알람 처리
6. 시스템 및 I/O 상태 확인
7. 운전·알람·설정 변경 로그 확인
8. 작업자 도움말 제공
9. 관리자용 유지보수 및 교정 기능

제어반의 물리 조작부는 다음과 같이 유지한다.

- Auto Run/Start
- Auto Stop
- Auto/Manual 셀렉터
- Manual Up
- Manual Down
- Main Power

HMI는 물리 Auto Start/Stop 및 Manual Up/Down 버튼을 중복 구현하지 않는다.

---

## 2. 핵심 운전 원칙

### 2.1 가압 자동 사이클

자동 사이클은 실린더 반복 가압만 수행한다.

```text
AUTO_IDLE
  → AUTO_PRECHECK
  → AUTO_MOVE_DOWN
  → AUTO_DWELL_DOWN
  → AUTO_MOVE_UP
  → AUTO_DWELL_UP
  → AUTO_COUNT_UPDATE
  → AUTO_COMPLETE 또는 다음 사이클
```

다음 항목은 자동 사이클에서 제외한다.

```text
- Vacuum ON
- Vacuum OK 대기
- Vacuum 유지 제어
- Blow-off
- Vacuum release 확인
```

자동 시퀀스는 진공 출력 상태를 변경해서는 안 된다.

### 2.2 진공 운전

진공은 작업자가 HMI 메인 화면에서 직접 ON/OFF한다.

```text
HMI Vacuum ON 명령
→ K_VACUUM_ON = ON
→ K_BLOW_OFF_ON = OFF
→ VACUUM_OK 상태 감시 및 표시

HMI Vacuum OFF 명령
→ K_VACUUM_ON = OFF
```

진공 명령은 자동 사이클 상태와 별도로 유지한다.

예:

```text
1. 작업자가 메인 화면에서 Vacuum ON
2. VACUUM_OK 확인
3. 물리 Auto Start 버튼으로 반복 가압 시작
4. 자동 사이클 중에도 Vacuum ON 유지
5. 자동 사이클 완료 후에도 Vacuum ON 유지
6. 작업자가 메인 화면에서 Vacuum OFF
```

자동운전 완료, 일시정지, Count Reset은 진공 출력을 자동으로 OFF하지 않는다.

단, Safety Stop, 통신 오류 또는 프로그램 종료 시에는 진공 출력을 강제 OFF한다.

---

## 3. 전체 화면 구성

하단 고정 메뉴는 다음 5개로 구성한다.

```text
[운전] [조건설정] [시스템상태] [로그] [도움말]
```

관리자 메뉴는 우측 상단 설정 아이콘에서 진입한다.

```text
설정
├─ 유지보수
├─ 하중 교정
├─ I/O 시험
├─ 통신 설정
└─ 시스템 설정
```

권장 페이지:

| 번호 | 페이지 | 주요 사용자 |
|---:|---|---|
| 0 | 부팅 및 초기점검 | 전체 |
| 1 | 메인 운전화면 | 작업자 |
| 2 | 운전 조건 설정 | 작업자/관리자 |
| 3 | 시스템 상태 | 작업자/관리자 |
| 4 | 로그 및 트렌드 | 작업자/관리자 |
| 5 | 도움말 | 전체 |
| 6 | 유지보수/I/O 시험 | 관리자/서비스 |
| 7 | 시스템 설정/교정 | 서비스 |

---

## 4. 공통 상태바

모든 페이지 상단에 공통 상태바를 표시한다.

```text
[반복 가압 측정기] [AUTO/MANUAL] [현재 상태] [현재 시각] [설정]
```

두 번째 줄에 핵심 장비 상태를 표시한다.

```text
SOL ENABLE | CYLINDER | VACUUM | LOADCELL | ADAM COMM
```

권장 표시 형식:

| 항목 | 정상 표시 | 중간 상태 | 이상 표시 |
|---|---|---|---|
| SOL ENABLE | ENABLED | RESET REQUIRED | DISABLED |
| Cylinder | UP / DOWN | MOVING | UNKNOWN |
| Vacuum | VACUUM OK | BUILDING | NOT OK / FAIL |
| Loadcell | NORMAL | ZERO REQUIRED | ERROR |
| ADAM | CONNECTED | RETRY | DISCONNECTED |

색상과 텍스트를 동시에 사용한다.

```text
● VACUUM OK
▲ VACUUM BUILDING
✕ VACUUM NOT OK
```

---

## 5. 메인 운전화면

### 5.1 화면 목적

메인 운전화면은 작업자가 실제 운전 중 가장 오래 보는 화면이다.

주요 표시항목:

- 현재 운전 모드
- 현재 장비 상태
- 현재 자동 시퀀스 단계
- 현재 하중
- 현재 사이클 최대 하중
- 전체 운전 최대 하중
- 목표 반복 횟수
- 현재 반복 횟수
- Down Dwell Time
- Up Dwell Time
- 실린더 위치
- 진공 명령 상태
- VACUUM_OK 입력 상태
- SOL_ENABLE 상태
- 활성 알람

### 5.2 메인 화면 초안

```text
┌──────────────────────────────────────────────────────┐
│ 반복 가압 측정기       AUTO       AUTO RUNNING      │
│ SOL ●  ADAM ●  LOADCELL ●  VACUUM ●                │
├──────────────────────┬───────────────────────────────┤
│ 현재 공정             │ 현재 하중                    │
│                      │                               │
│ CYLINDER DOWN        │        325.4 kgf             │
│ DWELL DOWN           │                               │
│ Remaining 1.2 s      │ 최대 하중 331.2 kgf          │
│                      │ 하중 상한 500.0 kgf          │
├──────────────────────┴───────────────────────────────┤
│ 반복 횟수  125 / 500       ███████░░░ 25.0%        │
│ Down 2.0 s  |  Up 1.0 s  |  Cycle 4.8 s            │
├──────────────────────────────────────────────────────┤
│ 진공 명령: ON       VACUUM_OK: ON                   │
│ [     VACUUM ON / OFF     ]                         │
├──────────────────────────────────────────────────────┤
│ [Safety Reset] [Alarm Clear] [Count Reset] [Zero]   │
├──────────────────────────────────────────────────────┤
│ 운전 | 조건설정 | 시스템상태 | 로그 | 도움말        │
└──────────────────────────────────────────────────────┘
```

### 5.3 진공 ON/OFF 버튼

메인 화면에 큰 토글 버튼을 배치한다.

버튼 표시 예:

```text
진공 OFF 상태:
[ VACUUM ON ]

진공 ON 상태:
[ VACUUM OFF ]
```

또는 상태를 포함한 단일 토글 형식으로 구현할 수 있다.

```text
[ VACUUM : ON ]
[ VACUUM : OFF ]
```

권장 사항:

- 현재 상태를 버튼 색상만으로 표현하지 않는다.
- 버튼 내부에 `ON` 또는 `OFF` 텍스트를 명확히 표시한다.
- 명령 상태와 입력 상태를 별도로 표시한다.

```text
Vacuum Command : ON
VACUUM_OK      : ON
```

`Vacuum Command = ON`인데 `VACUUM_OK = OFF`이면 진공 형성 중 또는 흡착 실패 상태로 판단한다.

---

## 6. 진공 수동 제어 로직

### 6.1 Vacuum ON 허용 조건

다음 조건을 모두 만족할 때만 Vacuum ON을 허용한다.

```text
SOL_ENABLE_OK = ON
ADAM-4055-C #2 communication = OK
No SAFETY_STOP
No ADAM_COMM_ERROR
K_BLOW_OFF_ON = OFF
```

Auto/Manual 셀렉터 위치와 관계없이 진공 수동 ON/OFF를 허용한다.

이유:

- 진공은 자동 가압 전에 작업자가 미리 ON할 수 있어야 한다.
- 자동 반복 가압 중에도 작업자가 필요에 따라 진공을 유지할 수 있어야 한다.
- 자동 시퀀스와 진공 수동 명령을 독립적으로 운용한다.

### 6.2 Vacuum OFF

Vacuum OFF는 정상 상태에서 항상 허용한다.

```text
HMI Vacuum OFF
→ K_VACUUM_ON = OFF
```

### 6.3 출력 인터락

```text
K_VACUUM_ON = ON  AND K_BLOW_OFF_ON = ON
→ 두 출력 모두 OFF
→ VACUUM_BLOWOFF_INTERLOCK 알람 발생
```

### 6.4 Safety Stop 처리

```text
SOL_ENABLE_OK = OFF
→ K_VALVE_DOWN = OFF
→ K_VALVE_UP = OFF
→ K_VACUUM_ON = OFF
→ K_BLOW_OFF_ON = OFF
→ vacuum_command_latched = OFF
→ state = SAFETY_STOP
```

Safety Reset 후 진공은 자동 복원하지 않는다.

```text
Safety Reset 완료
→ Vacuum Command는 OFF 상태 유지
→ 작업자가 Vacuum ON 버튼을 다시 눌러야 함
```

### 6.5 통신 오류 및 프로그램 종료

다음 경우 진공 출력을 강제 OFF한다.

```text
- ADAM-4055-C #2 통신 오류
- Raspberry Pi 프로그램 종료
- 프로그램 예외
- Raspberry Pi 재부팅
- Watchdog timeout
- 출력 쓰기 실패
```

복구 후에도 이전 Vacuum ON 명령을 자동 복원하지 않는다.

---

## 7. 진공 상태 판정

### 7.1 기본 상태

| Command | VACUUM_OK | 화면 상태 |
|---:|---:|---|
| OFF | OFF | Vacuum Off |
| ON | OFF | Vacuum Building |
| ON | ON | Vacuum OK |
| OFF | ON | Vacuum Residual 또는 입력 점검 필요 |

### 7.2 Vacuum ON Timeout

Vacuum ON 후 설정시간 내에 `VACUUM_OK`가 들어오지 않으면 경고 또는 알람을 발생시킨다.

권장 초기값:

```text
Vacuum confirm timeout: 2.0 s
```

처리안:

```text
Vacuum Command ON
→ 타이머 시작
→ VACUUM_OK = ON이면 타이머 종료
→ Timeout이면 VACUUM_NOT_REACHED 발생
```

진공 도달 실패 시 처리 기본안:

```text
- 자동 가압 사이클은 강제 정지하지 않음
- 메인 화면에 명확한 경고 표시
- 타워램프 Yellow 또는 Red 정책은 시운전 시 확정
- Vacuum Command는 기본적으로 ON 유지
- 작업자가 원인을 확인하고 OFF 또는 재시도
```

단, 향후 제품 낙하나 장비 손상 위험이 확인되면 `VACUUM_OK = OFF` 상태에서 Auto Start를 금지하는 옵션을 추가할 수 있다.

현재 버전에서는 진공과 자동 사이클을 논리적으로 독립시킨다.

---

## 8. Blow-off 처리

Blow-off는 자동 사이클에서 사용하지 않는다.

이번 HMI 기본 화면에는 Blow-off 버튼을 배치하지 않는다.

Blow-off 수동 시험은 관리자용 유지보수 페이지에서만 제공한다.

```text
Blow-off Test 버튼 누름
→ K_VACUUM_ON = OFF
→ 50~100 ms 대기
→ K_BLOW_OFF_ON = ON

버튼 해제 또는 최대시간 도달
→ K_BLOW_OFF_ON = OFF
```

권장 최대 시험시간:

```text
300 ms 또는 시운전 확정값
```

Blow-off 시험은 Hold-to-run 방식으로 구현한다.

---

## 9. 자동 시퀀스 상세

### 9.1 AUTO_PRECHECK

```text
MODE_AUTO = ON
SOL_ENABLE_OK = ON
No active blocking alarm
ADAM communication OK
Loadcell communication OK
Cylinder position valid
K_VALVE_DOWN = OFF
K_VALVE_UP = OFF
```

진공 관련 조건은 AUTO_PRECHECK의 필수 조건에서 제외한다.

```text
VACUUM_OK는 Auto Start 허가 조건이 아님
Vacuum Command 상태는 자동 시퀀스가 변경하지 않음
```

### 9.2 AUTO_MOVE_DOWN

```text
K_VALVE_DOWN = ON
K_VALVE_UP = OFF
CYL_DOWN_POS = ON 대기
Timeout 시 DOWN_TIMEOUT
```

### 9.3 AUTO_DWELL_DOWN

```text
K_VALVE_DOWN = OFF
K_VALVE_UP = OFF
DS6340 Closed Center
하중 모니터링
Down Dwell Time 유지
```

### 9.4 AUTO_MOVE_UP

```text
K_VALVE_DOWN = OFF
K_VALVE_UP = ON
CYL_UP_POS = ON 대기
Timeout 시 UP_TIMEOUT
```

### 9.5 AUTO_DWELL_UP

```text
K_VALVE_DOWN = OFF
K_VALVE_UP = OFF
Up Dwell Time 유지
```

### 9.6 AUTO_COUNT_UPDATE

```text
Current Count += 1

Current Count < Target Count
→ 다음 AUTO_MOVE_DOWN

Current Count >= Target Count
→ AUTO_COMPLETE
```

`AUTO_COMPLETE`에서도 Vacuum Command를 자동으로 변경하지 않는다.

---

## 10. 운전 조건 설정 페이지

표시 및 설정항목:

| 항목 | 형식 | 권장 기본값 |
|---|---|---:|
| 목표 반복 횟수 | 정수 | 500 |
| Down Dwell Time | 초 | 2.00 |
| Up Dwell Time | 초 | 1.00 |
| 하강 Timeout | 초 | 5.00 |
| 상승 Timeout | 초 | 5.00 |
| 하중 상한 | kgf | 시운전값 |
| Vacuum Confirm Timeout | 초 | 2.00 |
| 하중 데이터 저장 | ON/OFF | ON |

삭제할 자동운전 설정항목:

```text
- 자동 Vacuum 사용 ON/OFF
- 자동 Vacuum ON 시점
- 자동 Blow-off 유지시간
- 자동 Vacuum Release 대기
```

Vacuum Confirm Timeout은 수동 진공 명령의 상태 판정에만 사용한다.

설정 변경은 Idle 상태에서만 허용하는 것을 기본으로 한다.

---

## 11. 시스템 상태 페이지

### 11.1 상태 요약

```text
Controller
- Raspberry Pi application
- CPU temperature
- Storage free space
- Application uptime

Communication
- ADAM-4055-C #1
- ADAM-4055-C #2
- ADAM-4017+-F
- Polling cycle
- Retry count

Process
- SOL_ENABLE_OK
- Cylinder position
- Vacuum Command
- VACUUM_OK
- Loadcell current
- Converted load
```

### 11.2 ADAM-4055-C #2 표시

```text
DI-00 VACUUM_OK
DI-01 VACUUM_RELEASE_OK / SPARE
DI-02 AIR_PRESS_OK / SPARE
DI-03 VACUUM_UNIT_ALARM / SPARE

DO-00 K_VACUUM_ON
DO-01 K_BLOW_OFF_ON
```

출력은 다음 세 값을 구분하여 표시한다.

```text
Command
Permission
Actual written value
```

예:

```text
K_VACUUM_ON
Command    : ON
Permission : BLOCKED
Actual     : OFF
Reason     : SOL_ENABLE_OFF
```

---

## 12. 로그 구성

### 12.1 진공 명령 로그

다음 이벤트를 기록한다.

```text
VACUUM_COMMAND_ON
VACUUM_COMMAND_OFF
VACUUM_OK_ON
VACUUM_OK_OFF
VACUUM_NOT_REACHED
VACUUM_FORCED_OFF_SAFETY
VACUUM_FORCED_OFF_COMM_ERROR
VACUUM_FORCED_OFF_APP_SHUTDOWN
```

로그 항목:

| 항목 | 내용 |
|---|---|
| Timestamp | 발생 시각 |
| Event Code | 이벤트 코드 |
| Command State | Vacuum 명령 상태 |
| VACUUM_OK | 입력 상태 |
| SOL_ENABLE_OK | 안전허가 상태 |
| Auto State | 당시 자동 시퀀스 상태 |
| Operator | 사용자 정보 |
| Detail | 추가 설명 |

### 12.2 운전 로그

자동운전 로그에는 해당 운전 중 진공 상태를 참고 정보로 기록한다.

```text
Vacuum Command at Start
VACUUM_OK at Start
Vacuum Command at End
VACUUM_OK at End
Vacuum loss count during run
```

진공 상태는 자동운전 결과의 성공/실패를 직접 결정하지 않는다.

---

## 13. 알람 및 경고

| 코드 | 조건 | 처리 |
|---|---|---|
| `SAFETY_STOP` | SOL_ENABLE_OK OFF | 모든 액추에이터 출력 OFF |
| `ADAM_COMM_ERROR` | Remote I/O 통신 오류 | 모든 액추에이터 출력 OFF |
| `VACUUM_NOT_REACHED` | Vacuum ON 후 Timeout 내 VACUUM_OK 미입력 | 경고 표시 |
| `VACUUM_SIGNAL_ABNORMAL` | Vacuum OFF인데 VACUUM_OK 장시간 ON | 입력/배관 확인 경고 |
| `VACUUM_BLOWOFF_INTERLOCK` | Vacuum과 Blow-off 동시 명령 | 양쪽 출력 OFF |
| `DOWN_TIMEOUT` | 하강 위치 미도달 | 자동운전 정지 |
| `UP_TIMEOUT` | 상승 위치 미도달 | 자동운전 정지 |
| `LOAD_OVER_LIMIT` | 하중 상한 초과 | 밸브 출력 OFF 또는 상승 |
| `VALVE_INTERLOCK` | Up/Down 동시 명령 | 양쪽 출력 OFF |

`VACUUM_NOT_REACHED`는 현재 버전에서 자동운전을 강제로 정지시키는 Blocking Alarm이 아니라 Warning으로 처리한다.

---

## 14. Safety Reset

Safety Stop 화면:

```text
SAFETY STOP

액추에이터 구동 허가가 차단되었습니다.

1. 비상정지 버튼을 해제하십시오.
2. Area Sensor 감지영역을 확인하십시오.
3. SOL ENABLE 상태가 ON인지 확인하십시오.
4. Safety Reset을 누르십시오.
```

Reset 조건:

```text
state = SAFETY_STOP
AND SOL_ENABLE_OK = ON
AND HMI Safety Reset pressed
```

Reset 결과:

```text
Alarm latch clear
Valve outputs OFF 유지
Vacuum output OFF 유지
Auto state → AUTO_IDLE 또는 MANUAL_IDLE
자동 재시작 금지
진공 자동 복원 금지
```

---

## 15. 유지보수 페이지

관리자 권한에서 다음 기능을 제공한다.

```text
- Vacuum 수동 시험
- Blow-off 수동 시험
- Load Zero
- Load Span Calibration
- DI 상태 확인
- DO 시험
- Modbus 재연결
- 로그 내보내기
```

Vacuum 시험은 메인화면 진공 버튼과 동일한 출력 명령을 사용한다.

Blow-off 시험 조건:

```text
Maintenance permission
AND No auto running
AND SOL_ENABLE_OK
AND K_VACUUM_ON = OFF
```

화면 이탈 또는 권한 해제 시 모든 시험 출력을 OFF한다.

---

## 16. 소프트웨어 상태 변수 권장안

```python
mode_auto: bool
machine_state: str
sol_enable_ok: bool

vacuum_command: bool
vacuum_ok: bool
vacuum_confirm_timer_active: bool
vacuum_warning_active: bool

valve_down_command: bool
valve_up_command: bool
blowoff_command: bool

current_load_kgf: float
cycle_peak_load_kgf: float
run_peak_load_kgf: float

current_count: int
target_count: int
down_dwell_sec: float
up_dwell_sec: float
```

진공 명령은 자동 상태머신 변수와 분리한다.

```python
# 금지 예
machine_state == "AUTO_VACUUM_ON"

# 권장
vacuum_command = True  # HMI 수동 명령
machine_state = "AUTO_MOVE_DOWN"
```

---

## 17. 출력 처리 권장 구조

모든 액추에이터 출력은 한 함수에서 최종 결정한다.

```python
def write_actuator_outputs():
    valve_down = requested_valve_down
    valve_up = requested_valve_up
    vacuum_on = vacuum_command
    blowoff_on = requested_blowoff

    if not sol_enable_ok:
        valve_down = False
        valve_up = False
        vacuum_on = False
        blowoff_on = False

    if valve_down and valve_up:
        valve_down = False
        valve_up = False
        raise_alarm("VALVE_INTERLOCK")

    if vacuum_on and blowoff_on:
        vacuum_on = False
        blowoff_on = False
        raise_alarm("VACUUM_BLOWOFF_INTERLOCK")

    if not adam_4055_2_connected:
        vacuum_on = False
        blowoff_on = False

    adam4055_1.write_do(4, valve_down)
    adam4055_1.write_do(5, valve_up)
    adam4055_2.write_do(0, vacuum_on)
    adam4055_2.write_do(1, blowoff_on)
```

주의:

- `vacuum_command`는 사용자의 논리 명령값이다.
- 실제 출력값은 안전조건과 통신상태를 반영한 후 결정한다.
- HMI에는 명령값과 실제 출력값을 구분해 표시한다.

---

## 18. 저장 및 재부팅 정책

재부팅 시 복원 가능한 항목:

```text
- 목표 반복 횟수
- Down Dwell Time
- Up Dwell Time
- Timeout
- 하중 상한
- Vacuum Confirm Timeout
- 화면 밝기
- 로그 설정
```

재부팅 시 복원하지 않는 항목:

```text
- Vacuum Command
- Valve Command
- Blow-off Command
- Auto Running 상태
- Paused 상태
- Safety Reset 상태
```

프로그램 시작 시 기본값:

```text
K_VALVE_DOWN = OFF
K_VALVE_UP = OFF
K_VACUUM_ON = OFF
K_BLOW_OFF_ON = OFF
Vacuum Command = OFF
Machine State = INITIALIZING
```

---

## 19. 개발 우선순위

### 1차 구현

1. 부팅 및 통신 초기점검
2. 공통 상태바
3. 메인 운전화면
4. 메인 화면 Vacuum ON/OFF
5. 자동 반복 가압 상태머신
6. 운전 조건 설정
7. Safety Stop 및 Alarm Clear
8. 시스템 상태 요약
9. 알람 및 이벤트 로그
10. 도움말

### 2차 구현

1. 상세 I/O 모니터링
2. 하중 실시간 트렌드
3. 사이클별 하중 데이터 저장
4. 유지보수 Blow-off 시험
5. 로그 CSV 내보내기
6. 하중 교정
7. 사용자 권한
8. 진공 경고 정책 세부 설정

---

## 20. 개발 완료 판정 기준

### 20.1 진공 수동 제어

- 메인 화면에서 Vacuum ON/OFF가 가능해야 한다.
- Vacuum ON 상태에서 VACUUM_OK가 별도로 표시되어야 한다.
- 자동 사이클 시작·완료·정지로 진공 명령이 임의 변경되지 않아야 한다.
- Safety Stop 시 진공이 강제 OFF되어야 한다.
- 통신 오류 시 진공이 강제 OFF되어야 한다.
- Safety Reset 후 진공이 자동 복원되지 않아야 한다.
- 프로그램 재시작 후 진공이 OFF 상태여야 한다.

### 20.2 자동 가압

- 자동 시퀀스에 진공 관련 상태가 없어야 한다.
- 자동 시퀀스는 진공 DO를 쓰지 않아야 한다.
- 물리 Auto Start/Stop으로 운전 및 일시정지가 가능해야 한다.
- 목표 횟수까지 Down/Up 반복이 가능해야 한다.
- Down/Up 동시 출력이 차단되어야 한다.
- Timeout과 하중 상한 알람이 정상 작동해야 한다.

### 20.3 화면 및 로그

- 메인 화면에서 진공 명령과 실제 확인 상태가 구분되어야 한다.
- 진공 ON/OFF 및 강제 OFF 이력이 기록되어야 한다.
- 시스템 상태 페이지에서 ADAM 통신 및 진공 I/O를 확인할 수 있어야 한다.
- 작업자가 알람 원인과 조치방법을 도움말에서 확인할 수 있어야 한다.

---

## 21. 최종 변경 요약

```text
1. 진공은 HMI 메인 화면에서 작업자가 수동 ON/OFF한다.
2. 진공 명령은 Auto/Manual 셀렉터와 독립적으로 운용한다.
3. 진공 ON 상태에서도 자동 반복 가압을 시작할 수 있다.
4. 자동 가압 시퀀스에는 Vacuum ON, Vacuum Wait, Blow-off 단계를 넣지 않는다.
5. 자동운전 완료 또는 일시정지 시 진공 상태를 변경하지 않는다.
6. Safety Stop, 통신 오류, 프로그램 종료 시 진공을 강제 OFF한다.
7. 강제 OFF 후에는 작업자가 다시 Vacuum ON을 눌러야 한다.
8. Blow-off는 자동운전에서 제외하고 관리자 유지보수 화면에서만 시험한다.
9. 메인 화면에는 Vacuum Command와 VACUUM_OK를 별도로 표시한다.
10. 자동 상태머신과 진공 수동 명령 로직을 분리하여 구현한다.
```
