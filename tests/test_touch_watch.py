"""TouchWatch: 터치 USB 재열거(devnum 변화) 감지·카운트·복구콜백·쿨다운."""

import control_system.hardware.touch_watch as twmod


def _watch(monkeypatch, start, on_reenum=None, cooldown_s=0.0):
    box = {"n": start}
    monkeypatch.setattr(twmod.TouchWatch, "_read_devnum", lambda self: box["n"])
    tw = twmod.TouchWatch("0eef:0005", on_reenum=on_reenum, cooldown_s=cooldown_s)
    return tw, box


def test_counts_only_on_change(monkeypatch):
    calls = []
    tw, box = _watch(monkeypatch, "8", on_reenum=lambda: calls.append(1))
    assert tw.count == 0
    assert tw.poll() is False            # 변화 없음
    box["n"] = "9"
    assert tw.poll() is True             # 재열거
    assert tw.count == 1 and len(calls) == 1
    assert tw.poll() is False            # 같은 값 → 무시
    box["n"] = "10"
    assert tw.poll() is True
    assert tw.count == 2 and len(calls) == 2


def test_absent_device_no_count(monkeypatch):
    tw, box = _watch(monkeypatch, None)
    box["n"] = None
    assert tw.poll() is False
    assert tw.count == 0


def test_cooldown_suppresses_self_induced(monkeypatch):
    """복구콜백이 유발한 재열거(쿨다운 내)는 카운트/재발동하지 않는다."""
    calls = []
    tw, box = _watch(monkeypatch, "8", on_reenum=lambda: calls.append(1), cooldown_s=9999.0)
    box["n"] = "9"
    assert tw.poll() is True             # 첫 재열거 → 복구 1회
    assert tw.count == 1 and len(calls) == 1
    box["n"] = "10"                       # 복구로 인한 재열거(쿨다운 내)
    assert tw.poll() is False
    assert tw.count == 1 and len(calls) == 1
