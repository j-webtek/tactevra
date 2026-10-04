"""r90 one-use app-only installer exercised with fake serial and flash."""

import hashlib
import sys
from types import ModuleType, SimpleNamespace

import pytest

from scripts import deploy_r90_pose_hover as deploy


def _installer_fixture(tmp_path):
    """Build non-authority inputs for installer sequencing tests.

    The retained app bytes still exercise the installer's readback hash check;
    historical release preflight remains a separate fail-closed test boundary.
    """
    root = deploy.Path(__file__).resolve().parents[2]
    image_path = (root / ".firmware-tools"
                  / "build-configured-diagnostic-candidate-r90--default-4mb-no-psram"
                  / "RoArm-M3_example.ino.bin")
    prior_path = (root / ".firmware-tools"
                  / "build-configured-diagnostic-candidate-r89--default-4mb-no-psram"
                  / "RoArm-M3_example.ino.bin")
    return dict(image=image_path.read_bytes(), image_path=image_path,
                prior=prior_path.read_bytes(), partition_md5="1" * 32,
                filesystem_md5="2" * 32, journal=tmp_path / "attempt.jsonl",
                release_sha256="3" * 64)


@pytest.mark.parametrize("predecessor_matches", [True, False])
def test_r90_installer_never_writes_before_predecessor_check(monkeypatch, tmp_path,
                                                               predecessor_matches):
    root = deploy.Path(__file__).resolve().parents[2]
    prepared = _installer_fixture(tmp_path)
    calls = dict(write=0, reset=0, port_open=0, port_close=0)

    class Stub:
        def flash_id(self):
            return 0x164020

        def flash_md5sum(self, start, size):
            if (start, size) == (0x10000, len(prepared["prior"])):
                return (hashlib.md5(prepared["prior"]).hexdigest()
                        if predecessor_matches else "0" * 32)
            if (start, size) == (0x8000, 3072):
                return prepared["partition_md5"]
            if (start, size) == (0x290000, 0x160000):
                return prepared["filesystem_md5"]
            if (start, size) in ((0, 0x10000), (0x150000, 0x2b0000)):
                return "a" * 32
            raise AssertionError("Unreviewed flash region")

        def read_flash(self, start, length):
            assert (start, length) == (0x10000, len(prepared["image"]))
            return prepared["image"]

        def hard_reset(self):
            calls["reset"] += 1

    stub = Stub()

    class Esp:
        secure_download_mode = False
        stub_is_disabled = False

        def connect(self, mode, attempts):
            assert (mode, attempts) == ("default_reset", 1)

        def read_mac(self):
            return bytes.fromhex("fce8c0f8d538")

        def get_secure_boot_enabled(self):
            return False

        def get_flash_encryption_enabled(self):
            return False

        def run_stub(self):
            return stub

    class Port:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def open(self):
            calls["port_open"] += 1

        def close(self):
            calls["port_close"] += 1

    serial = ModuleType("serial")
    serial.__path__ = []
    serial.Serial = Port
    tools = ModuleType("serial.tools")
    tools.__path__ = []
    ports = ModuleType("serial.tools.list_ports")
    ports.comports = lambda: [SimpleNamespace(device="COM7", vid=0x10c4,
                                              pid=0xea60, serial_number=deploy.USB_SERIAL)]
    esptool = ModuleType("esptool")
    esptool.__version__ = "4.6"
    esptool.__file__ = str(root / ".firmware-tools/esptool-api-4.6/esptool/__init__.py")
    cmds = ModuleType("esptool.cmds")

    def write_flash(device, args):
        assert device is stub
        assert len(args.addr_filename) == 1
        assert args.addr_filename[0][0] == 0x10000
        assert args.addr_filename[0][1].read() == prepared["image"]
        assert args.erase_all is False and args.encrypt is False
        calls["write"] += 1

    cmds.write_flash = write_flash
    loader = ModuleType("esptool.loader")
    esptool.cmds = cmds
    esptool.loader = loader
    monkeypatch.setattr(deploy, "longer_reset_rom", lambda _esptool, port: Esp())
    for name, module in (("serial", serial), ("serial.tools", tools),
                         ("serial.tools.list_ports", ports), ("esptool", esptool),
                         ("esptool.cmds", cmds), ("esptool.loader", loader)):
        monkeypatch.setitem(sys.modules, name, module)

    if predecessor_matches:
        deploy.install(root, prepared)
        assert calls == dict(write=1, reset=1, port_open=1, port_close=1)
        assert '"stage": "FLASH_VERIFIED"' in prepared["journal"].read_text()
    else:
        with pytest.raises(ValueError, match="Installed predecessor"):
            deploy.install(root, prepared)
        assert calls == dict(write=0, reset=0, port_open=1, port_close=1)
        assert '"stage": "STOPPED"' in prepared["journal"].read_text()
