#!/bin/sh
# 터치 USB 재설정 — 지정 VID:PID 장치를 재열거(authorized 토글)해 먹통 터치를 되살린다.
# 앱(HMI)이 'AUTO + 수동 상승·하강 2초 동시' 제스처 감지 시 sudo 로 이 스크립트를 호출한다.
#
# [설치]  현장에서 1회:
#   1) 터치 컨트롤러 VID:PID 확인:  lsusb        (예: "ID 222a:0001 ...")
#   2) 아래 TOUCH_VIDPID 를 그 값으로 수정.
#   3) sudo install -m 0755 deploy/reset-touch.sh /usr/local/bin/reset-touch.sh
#   4) sudo install -m 0440 deploy/reset-touch.sudoers /etc/sudoers.d/reset-touch
#   5) 테스트:  sudo -n /usr/local/bin/reset-touch.sh ; echo $?
set -eu

TOUCH_VIDPID="222a:0001"     # TODO: 현장 터치 컨트롤러 VID:PID 로 수정 (lsusb 로 확인)

vid="${TOUCH_VIDPID%%:*}"
pid="${TOUCH_VIDPID##*:}"

found=""
for d in /sys/bus/usb/devices/*; do
    [ -f "$d/idVendor" ] && [ -f "$d/idProduct" ] || continue
    if [ "$(cat "$d/idVendor")" = "$vid" ] && [ "$(cat "$d/idProduct")" = "$pid" ]; then
        found="$d"
        break
    fi
done

if [ -z "$found" ]; then
    echo "touch device not found: $TOUCH_VIDPID" >&2
    exit 1
fi

# authorized 0 -> 1 로 재열거(권한: root). 커널이 장치를 다시 붙이고 libinput 이 재인식.
echo 0 > "$found/authorized"
sleep 1
echo 1 > "$found/authorized"
echo "touch reset: $found ($TOUCH_VIDPID)"

# (대안) 위로 안 되면 usbutils 의 usbreset, 또는 compositor 재시작을 README 참고.
