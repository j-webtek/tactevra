from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[2]


def _module(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    import deploy_r119_commanded_approach_latch

    return deploy_r119_commanded_approach_latch


def test_r119_installer_prepares_exact_compiled_pair_without_hardware(monkeypatch, tmp_path):
    module = _module(monkeypatch)
    for candidate in ("r118", "r119"):
        name = f"build-configured-diagnostic-candidate-{candidate}--default-4mb-no-psram"
        destination = tmp_path / ".firmware-tools" / name
        destination.mkdir(parents=True)
        shutil.copy2(ROOT / ".firmware-tools" / name / "RoArm-M3_example.ino.bin", destination)
    prepared = module.prepare(tmp_path)
    assert module._sha256(prepared["previous"]) == module.PREVIOUS_SHA256
    assert module._sha256(prepared["image"]) == module.CURRENT_SHA256
    assert prepared["journal"].name == "app-r119-deployment-events.jsonl"


def test_r119_installer_is_app_only_and_has_no_motion_payload(monkeypatch):
    module = _module(monkeypatch)
    source = Path(module.__file__).read_text(encoding="utf-8")
    assert "addr_filename=[(0x10000, stream)]" in source
    assert "WRITE_BLOCK_ATTEMPTS = 1" in source
    assert '"T":' not in source
    assert "SyncWritePosEx" not in source
