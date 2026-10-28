import importlib.util
from pathlib import Path

import pytest

FILE = Path(__file__).resolve().parents[1] / "tools/launch_additional_qwen_v073.py"
spec = importlib.util.spec_from_file_location("additional_qwen_v073", FILE)
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def test_capacity_selection_prefers_7_then_0_and_excludes_active():
    cards = [{"gpu_index": index, "gpu_uuid": f"uuid-{index}", "free_mib": 81152}
             for index in (2, 0, 5, 7)]
    result = launcher.choose_targets(cards, [{"gpu_uuid": "uuid-2"}])
    assert result == {4: {"gpu_index": 7, "gpu_uuid": "uuid-7"},
                      5: {"gpu_index": 0, "gpu_uuid": "uuid-0"}}
    with pytest.raises(launcher.policy.ResourceBusy):
        launcher.choose_targets(cards[:2], [{"gpu_uuid": "uuid-2"}])


def test_all_local_functions_share_new_namespace_without_altering_v071(tmp_path, monkeypatch):
    original = launcher.original_launcher()
    original_targets = dict(original.TARGETS)
    monkeypatch.setattr(launcher, "OUT", tmp_path)
    targets = {4: {"gpu_index": 7, "gpu_uuid": "uuid-7"}, 5: {"gpu_index": 0, "gpu_uuid": "uuid-0"}}
    namespace = launcher.bind_launcher(targets)
    for name in ("prepare", "launch", "launch_one", "authorization_file", "validate_authorization", "selected_indices"):
        assert namespace[name].__globals__ is namespace
    assert namespace["authorization_file"](4) == tmp_path / "model-4-authorization.json"
    assert namespace["VERSION"] == launcher.VERSION and namespace["TARGETS"] == targets
    assert namespace["__file__"] == str(FILE)
    assert original.TARGETS == original_targets and original.OUT != tmp_path
