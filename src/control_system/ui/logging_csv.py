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
