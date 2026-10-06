터치 먹통 복구 (물리 버튼 제스처 → 터치 USB 재설정)
=====================================================

증상: USB 재열거 노이즈로 터치가 먹통(화면은 정상, 터치 무반응). 물리 버튼/DIO 는 동작.

복구 제스처(운영자):
  AUTO 모드에서 "Manual Up + Manual Down" 을 동시에 약 2초 누름
  → 비프음 1회(확인) 후 터치 USB 가 재설정되어 터치가 되살아남.
  (AUTO 에서 수동 버튼은 실린더를 움직이지 않으므로 안전. 손을 떼야 다시 쓸 수 있음.)
  * 유지시간은 TOUCH_RESET_HOLD(초) 환경변수로 조정, 0 이면 비활성.

동작 원리: 터치가 죽어도 ADAM DIO(시리얼)는 살아있어 앱 스캔 루프가 두 버튼을 읽는다.
제스처를 감지하면 앱이 sudo 로 reset-touch.sh 를 실행해 터치 USB 를 재열거한다.

[현장 설치] (파이, 1회, sudo 필요)
  1) 터치 컨트롤러 VID:PID 확인:
        lsusb
     예) "Bus 001 Device 005: ID 222a:0001 ..."  → 222a:0001
  2) deploy/reset-touch.sh 의 TOUCH_VIDPID 를 그 값으로 수정.
  3) 설치:
        sudo install -m 0755 deploy/reset-touch.sh      /usr/local/bin/reset-touch.sh
        sudo install -m 0440 deploy/reset-touch.sudoers  /etc/sudoers.d/reset-touch
        sudo visudo -cf /etc/sudoers.d/reset-touch        # 문법 OK 확인
  4) 수동 테스트:
        sudo -n /usr/local/bin/reset-touch.sh ; echo exit=$?
     (터치가 잠깐 끊겼다 재인식되면 성공)
  5) 앱 재시작 후, AUTO 에서 제스처로 동작 확인.

환경변수(유저 서비스 ~/.config/systemd/user/control-system.service 의 Environment):
  TOUCH_RESET_HOLD=2        # 제스처 유지시간(초), 0=비활성
  TOUCH_RESET_CMD=/usr/local/bin/reset-touch.sh   # 스크립트 경로(기본값과 같으면 불필요)

안 될 때(에스컬레이션):
  - authorized 토글로 안 살아나면 reset-touch.sh 에서 usbreset(usbutils) 또는
    unbind/bind(/sys/bus/usb/drivers/usb/) 방식으로 교체.
  - 그래도 안 되면 compositor(labwc) 재시작이 필요할 수 있음:
        systemctl --user restart control-system.service  (앱만) — 단 터치 재인식엔 부족할 수 있어
    labwc 세션 재시작/재로그인이 확실. 근본 대책은 HW 노이즈 억제(스너버/페라이트/배선분리).
