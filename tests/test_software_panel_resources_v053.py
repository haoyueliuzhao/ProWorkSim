import pytest

from proworksim.software_panel_resources_v053 import select_cards


def test_shared_a800_admission_uses_actual_capacity_and_excludes_active_workers():
    cards = [{"index": i, "uuid": f"GPU-{i}", "name": "NVIDIA A800-SXM4-80GB",
              "free_mib": free, "total_mib": 81920, "utilization_percent": 99}
             for i, free in enumerate((46079, 46080, 50000))]
    assert [x["index"] for x in select_cards(cards)] == [2, 1]
    assert [x["index"] for x in select_cards(cards, excluded={2})] == [1]
    with pytest.raises(ValueError, match="Duplicate"):
        select_cards([cards[0], cards[0]])
