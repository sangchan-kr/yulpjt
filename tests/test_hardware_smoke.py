"""Phase A 하드웨어 계층 스모크 테스트 (mock 전용, 서드파티 의존성 없음).

pytest 로도, `python tests/test_hardware_smoke.py` 로도 실행된다.
"""

import os
import sys
import tempfile

# 설치 없이 실행할 수 있게 src 를 경로에 추가.
_SRC = os.path.join(os.path.dirname(__file__), "..", "src")
if _SRC not in sys.path:
    sys.path.insert(0, os.path.abspath(_SRC))

from control_system.config import Config
from control_system.hardware.adam4017 import Adam4017
from control_system.hardware.adam4055 import Adam4055
from control_system.hardware.loadcell import LoadCell
from control_system.hardware.signals import AI, DI1, DI2, DO1, DO2, IO


def _build(mock_invert_vacuum=False):
    cfg = Config()
    a1 = Adam4055(None, cfg.node_adam1, mock=True, name="#1")
    a2 = Adam4055(None, cfg.node_adam2, mock=True, name="#2")
    ai = Adam4017(None, cfg.node_adam4017, mock=True)
    invert = {DI2.VACUUM_OK} if mock_invert_vacuum else frozenset()
    io = IO(a1, a2, ai, input_invert=invert)
    return cfg, a1, a2, ai, io


def test_recipe_store_put_get_persist():
    """레시피 3슬롯: 저장/조회/디스크 영속 (F1)."""
    from control_system.config import RecipeStore, RuntimeSettings
    tmp = os.path.join(tempfile.gettempdir(), "recipes_test.json")
    if os.path.exists(tmp):
        os.remove(tmp)
    rs = RecipeStore.load(tmp)
    assert rs.N == 3 and not rs.is_set(0)
    vals = {k: getattr(RuntimeSettings(), k) for k in RuntimeSettings._EDITABLE}
    vals["target_count"] = 123
    rs.put(1, vals)
    assert rs.is_set(1) and rs.get(1)["target_count"] == 123
    assert not rs.is_set(0) and not rs.is_set(2)
    # 재로드 영속
    rs2 = RecipeStore.load(tmp)
    assert rs2.is_set(1) and rs2.get(1)["target_count"] == 123
    assert not rs2.is_set(0)


def test_input_invert_channel_isolation():
    """한 모듈 채널만 반전 지정해도 다른 모듈 같은 채널이 함께 반전되면 안 됨.

    DI1/DI2 는 IntEnum 이라 채널이 겹치면(MODE_AUTO=0, VACUUM_OK=0) == 로 같게 판정된다.
    (타입,채널) 키로 저장해 격리해야 한다.
    """
    a1 = Adam4055(None, 1, mock=True)
    a2 = Adam4055(None, 2, mock=True)
    ai = Adam4017(None, 3, mock=True)
    io = IO(a1, a2, ai, input_invert={DI1.MODE_AUTO})   # DI1 ch0 만 반전
    a1.set_mock_di(int(DI1.MODE_AUTO), True)
    a2.set_mock_di(int(DI2.VACUUM_OK), True)
    io.refresh_inputs()
    assert io.di(DI1.MODE_AUTO) is False       # 반전됨
    assert io.di(DI2.VACUUM_OK) is True        # 반전 안 됨(충돌 격리)


def test_hub_reconnects_on_usb_dropout():
    """USB 재열거로 fd 가 죽으면(OSError) 포트를 재오픈하고 재시도해 복구한다."""
    from control_system.hardware.modbus_hub import AdamSerialBus

    class _Dead:                      # 죽은 포트: 접근하면 OSError
        is_open = True
        def reset_input_buffer(self): raise OSError("device disconnected")
        def close(self): pass

    class _Live:                      # 재열거 후 정상 포트: "!01000000\r" 응답
        is_open = True
        def __init__(self): self._b = b"!01000000\r"; self._i = 0
        def reset_input_buffer(self): pass
        def write(self, b): pass
        def read(self, n):
            if self._i < len(self._b):
                c = self._b[self._i:self._i + 1]; self._i += 1; return c
            return b""
        def close(self): pass

    bus = AdamSerialBus("/dev/serial/by-id/usb-CP210x-if00-port0", 9600, retries=1)
    bus._ser = _Dead()
    bus._resolve_port = lambda: bus._port          # 실제 파일시스템 접근 회피
    bus.connect = lambda: (setattr(bus, "_ser", _Live()) or True)
    assert bus.command("$016") == "!01000000"      # 첫 시도 실패→재오픈→성공


def test_loadcell_conversion():
    cfg, a1, a2, ai, io = _build()
    tmp = os.path.join(tempfile.gettempdir(), "cal_test.json")
    if os.path.exists(tmp):
        os.remove(tmp)
    lc = LoadCell(ai, cfg.loadcell_ai_channel, cfg.loadcell_full_scale_kgf, tmp)

    # 4 mA → 0 kgf, 20 mA → 1000 kgf, 12 mA → 500 kgf
    ai.set_mock_ma(0, 4.0)
    assert abs(lc.read_kgf() - 0.0) < 1e-6, lc.read_kgf()
    ai.set_mock_ma(0, 20.0)
    assert abs(lc.read_kgf() - 1000.0) < 1e-6, lc.read_kgf()
    ai.set_mock_ma(0, 12.0)
    assert abs(lc.read_kgf() - 500.0) < 1e-6, lc.read_kgf()


def test_loadcell_tare_and_persist():
    cfg, a1, a2, ai, io = _build()
    tmp = os.path.join(tempfile.gettempdir(), "cal_test2.json")
    if os.path.exists(tmp):
        os.remove(tmp)
    lc = LoadCell(ai, 0, cfg.loadcell_full_scale_kgf, tmp)

    ai.set_mock_ma(0, 5.0)              # 62.5 kgf 상당
    lc.tare()                          # 영점 = 62.5
    assert abs(lc.read_kgf()) < 1e-6   # tare 직후 0
    ai.set_mock_ma(0, 6.0)             # +62.5 kgf
    assert abs(lc.read_kgf() - 62.5) < 1e-6, lc.read_kgf()

    # 새 인스턴스가 저장된 zero_offset 을 복원하는지
    lc2 = LoadCell(ai, 0, cfg.loadcell_full_scale_kgf, tmp)
    assert abs(lc2.zero_offset - 62.5) < 1e-6, lc2.zero_offset


def test_loadcell_wire_break():
    cfg, a1, a2, ai, io = _build()
    lc = LoadCell(ai, 0, cfg.loadcell_full_scale_kgf, os.path.join(tempfile.gettempdir(), "cal_x.json"))
    ai.set_mock_ma(0, 4.5)
    assert lc.current_valid()
    ai.set_mock_ma(0, 0.0)             # 단선
    assert not lc.current_valid()


def test_loadcell_calibrate_span():
    cfg, a1, a2, ai, io = _build()
    tmp = os.path.join(tempfile.gettempdir(), "cal_span.json")
    if os.path.exists(tmp):
        os.remove(tmp)
    lc = LoadCell(ai, 0, cfg.loadcell_full_scale_kgf, tmp)
    ai.set_mock_ma(0, 7.2)                 # (7.2-4)/16*1000 = 200 kgf raw
    assert abs(lc.read_raw_kgf() - 200.0) < 1e-6
    assert lc.calibrate_span(100.0) is True  # 기준 100 → scale 0.5
    assert abs(lc.scale - 0.5) < 1e-6
    assert abs(lc.read_kgf() - 100.0) < 1e-6


def test_di_named_read():
    cfg, a1, a2, ai, io = _build()
    a1.set_mock_di(int(DI1.MODE_AUTO), True)
    a1.set_mock_di(int(DI1.SOL_ENABLE_OK), True)
    a2.set_mock_di(int(DI2.VACUUM_OK), True)
    io.refresh_inputs()
    assert io.di(DI1.MODE_AUTO) is True
    assert io.di(DI1.AUTO_START_PB) is False
    assert io.di(DI1.SOL_ENABLE_OK) is True
    assert io.di(DI2.VACUUM_OK) is True


def test_di_inversion():
    cfg, a1, a2, ai, io = _build(mock_invert_vacuum=True)
    a2.set_mock_di(int(DI2.VACUUM_OK), False)   # NPN: 하드웨어 False 지만 반전되어 True
    io.refresh_inputs()
    assert io.di(DI2.VACUUM_OK) is True
    a2.set_mock_di(int(DI2.VACUUM_OK), True)
    io.refresh_inputs()
    assert io.di(DI2.VACUUM_OK) is False


def test_do_stage_flush():
    cfg, a1, a2, ai, io = _build()
    io.set(DO1.K_VALVE_DOWN, True)
    io.set(DO2.K_VACUUM_ON, True)
    # flush 전에는 모듈에 반영 안 됨
    assert a1.read_do()[int(DO1.K_VALVE_DOWN)] is False
    io.flush_outputs()
    assert a1.read_do()[int(DO1.K_VALVE_DOWN)] is True
    assert a2.read_do()[int(DO2.K_VACUUM_ON)] is True
    assert a1.read_do()[int(DO1.K_VALVE_UP)] is False

    # all_outputs_off + flush → 전부 OFF
    io.all_outputs_off()
    io.flush_outputs()
    assert not any(a1.read_do())
    assert not any(a2.read_do())


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        print(f"  PASS  {fn.__name__}")
        passed += 1
    print(f"\n{passed}/{len(fns)} passed")


if __name__ == "__main__":
    _run_all()
