"""운전 데이터 CSV 로거 (v1.12 §1-9).

가압 1사이클이 끝날 때(카운트 증가) 시각·카운트·최대하중·알람을 append 한다.
파일은 data/ 아래에 쌓이며 .gitignore 로 무시된다.
"""

import csv
import datetime
import os


class CsvLogger:
    HEADER = ["timestamp", "count", "max_load_kgf", "alarms"]

    def __init__(self, path: str = "data/run_log.csv") -> None:
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        if not os.path.exists(path):
            with open(path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(self.HEADER)

    def log_cycle(self, count: int, max_load_kgf: float, alarms) -> None:
        ts = datetime.datetime.now().isoformat(timespec="seconds")
        alarm_str = ";".join(sorted(a.value for a in alarms))
        with open(self.path, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([ts, count, f"{max_load_kgf:.1f}", alarm_str])


class EventLog:
    """메모리 상 이벤트/알람 링버퍼 (로그 페이지 표시용).

    상태 변화, 알람 발생/해제, 진공 명령/경고 변화를 시각과 함께 기록한다.
    """

    def __init__(self, maxlen: int = 300) -> None:
        self.maxlen = maxlen
        self._items: list[tuple[str, str, str]] = []   # (time, code, detail)

    def add(self, code: str, detail: str = "") -> None:
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self._items.append((ts, code, detail))
        if len(self._items) > self.maxlen:
            self._items = self._items[-self.maxlen:]

    def recent(self, n: int = 30, codes=None) -> list[tuple[str, str, str]]:
        """최근 항목(최신순). codes 를 주면 해당 code 만 필터링 후 최근 n개."""
        items = self._items if codes is None else [x for x in self._items if x[1] in codes]
        return list(reversed(items[-n:]))
