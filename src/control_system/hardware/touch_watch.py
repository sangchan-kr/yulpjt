"""터치스크린 USB 재열거 감시 (sudo 불필요, /sys 읽기만).

노이즈로 터치 컨트롤러 USB 가 재열거되면(기기 번호가 바뀌면) 터치 입력이 끊긴다.
sysfs 의 devnum(열거할 때마다 1 증가)을 폴링해 재열거를 감지·카운트하고,
콜백으로 복구(USB 재설정)를 건다. CP2103(통신)의 "재접속"과 대응되는 터치판.

- VID:PID 로 /sys/bus/usb/devices 에서 장치를 찾는다(터치=0eef:0005, WaveShare WS170120).
- 복구 콜백이 스스로 재열거를 유발(authorized 토글 등)하므로, 복구 직후 cooldown 동안은
  재열거를 무시해 자기 자신으로 인한 루프/중복 카운트를 막는다.
"""

import glob
import logging
import time


class TouchWatch:
    def __init__(self, vidpid: str = "0eef:0005", on_reenum=None,
                 cooldown_s: float = 10.0) -> None:
        vid, _, pid = vidpid.lower().partition(":")
        self._vid, self._pid = vid, pid
        self._on_reenum = on_reenum
        self._cooldown_s = cooldown_s
        self.count = 0
        self._last_devnum = self._read_devnum()
        self._suppress_until = 0.0

    def _find_dir(self):
        for d in glob.glob("/sys/bus/usb/devices/*"):
            try:
                with open(d + "/idVendor") as f:
                    if f.read().strip().lower() != self._vid:
                        continue
                with open(d + "/idProduct") as f:
                    if f.read().strip().lower() != self._pid:
                        continue
                return d
            except OSError:
                continue
        return None

    def _read_devnum(self):
        d = self._find_dir()
        if d is None:
            return None
        try:
            with open(d + "/devnum") as f:
                return f.read().strip()
        except OSError:
            return None

    def poll(self) -> bool:
        """주기 호출. 새 재열거가 감지되면 True(+카운트·복구콜백). 장치 부재/불변은 False."""
        devnum = self._read_devnum()
        if devnum is None or devnum == self._last_devnum:
            return False
        prev, self._last_devnum = self._last_devnum, devnum
        now = time.monotonic()
        if now < self._suppress_until:
            return False                      # 복구로 인한 자체 재열거 — 무시
        self.count += 1
        logging.getLogger("event").warning(
            "터치 USB 재열거 감지 (#%d, devnum %s→%s) → 복구 시도",
            self.count, prev, devnum)
        if self._on_reenum is not None:
            self._suppress_until = now + self._cooldown_s
            try:
                self._on_reenum()
            except Exception:                 # noqa: BLE001
                logging.getLogger("hmi").exception("터치 재열거 복구 콜백 실패")
        return True
