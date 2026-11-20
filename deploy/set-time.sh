#!/bin/sh
# HMI(유지보수 '시스템 시간' 메뉴)가 sudo -n 으로 호출하는 시간설정 헬퍼.
# 오프라인(파이에 인터넷/NTP 없음) 환경에서 작업자가 화면으로 시계를 맞출 수 있게 한다.
# 인자: "YYYY-MM-DD HH:MM:SS" — 시스템 시간 설정 + RTC + fake-hwclock 기록.
#
# [설치] (파이, 1회, sudo 필요):
#   sudo install -m 0755 deploy/set-time.sh      /usr/local/bin/set-time.sh
#   sudo install -m 0440 deploy/set-time.sudoers  /etc/sudoers.d/set-time
#   sudo visudo -cf /etc/sudoers.d/set-time        # 문법 검증
set -eu
[ -n "${1:-}" ] || { echo "시간 인자 없음" >&2; exit 1; }
date -s "$1" >/dev/null
hwclock -w 2>/dev/null || true        # RTC 기록(배터리 있으면 전원 꺼도 유지)
fake-hwclock save 2>/dev/null || true # 다음 부팅 복원값 갱신
exit 0
