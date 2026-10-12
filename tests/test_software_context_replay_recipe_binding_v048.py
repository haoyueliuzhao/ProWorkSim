"""Only the v047 metadata binding; no tokenizer, model or world is loaded."""
import copy
from pathlib import Path

import pytest

from proworksim.storage import read_json
from scripts.software_context_replay_v048 import CAPACITY_BINDING_PATH, bind_native_recipe

ROOT = Path(__file__).resolve().parents[1]
OWNER = ROOT / "runs/software-model-selection-v030/qwen3.5-9b/actual/resident/owner.json"


def test_recorded_member_metadata_and_capacity_restore_exact_recipe():
    owner, binding = read_json(OWNER), read_json(CAPACITY_BINDING_PATH)
    result = bind_native_recipe(owner["recipe"], owner["inference_profile"], binding)
    assert result == binding["capacity_recipe"]
    assert owner["recipe"]["members"] == ["provider", "implementer", "reviewer"]


def test_nonmember_recipe_difference_is_rejected():
    owner, binding = read_json(OWNER), read_json(CAPACITY_BINDING_PATH)
    altered = copy.deepcopy(binding)
    altered["original_recipe"]["temperature"] += 0.1
    with pytest.raises(ValueError, match="beyond the recorded members migration"):
        bind_native_recipe(owner["recipe"], owner["inference_profile"], altered)
