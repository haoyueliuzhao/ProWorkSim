"""Six fixed treatments and no real evaluation authority, using CPU only."""
import json

import pytest

from proworksim import software_fixed_organization_v065 as catalog

COUNTS = {"CHIEF": 4, "SOP": 3, "DIALOGUE": 2, "REVIEW": 2, "PEER": 4, "COUNCIL": 3}
GROUPS = ("CHIEF", "SOP", "DIALOGUE", "REVIEW", "PEER", "COUNCIL")


def test_catalog_has_six_representative_fixed_two_to_four_member_treatments():
    organizations = catalog.catalog()
    assert {row["id"] for row in organizations} == set(GROUPS)
    treatments = set()
    for row in organizations:
        members = tuple(f"member_{index:03d}" for index in range(1, COUNTS[row["id"]] + 1))
        assert row["member_count"] == len(members)
        assert set(row["fixed_members"]) == set(members)
        assert set(row["roles"]) == set(members)
        assert row["delivery_member"] == "member_001"
        assert all(a in members and b in members and a != b for a, b in row["communication_edges"])
        assert all(set(phase["active_members"]) <= set(members) and phase["opportunities"] > 0
                   for phase in row["phases"])
        treatments.add(json.dumps({"edges": row["communication_edges"], "phases": row["phases"]}, sort_keys=True))
        assert catalog.validate_organization(row) == row
    assert len(treatments) == 6
    changed = catalog.get_organization("CHIEF")
    changed["roles"]["member_001"]["title"] = "replacement role"
    assert catalog.get_organization("CHIEF") != changed
    with pytest.raises(ValueError):
        catalog.validate_organization(changed)



def test_review_catalog_cannot_enable_real_evaluation():
    assert catalog.COMMON["real_evaluation_enabled"] is False
    assert catalog.COMMON["team_token_budget"] is None
    assert catalog.COMMON["new_model_calls_authorized"] == 0
    assert catalog.COMMON["new_api_cash_authorized_CNY"] == 0
    with pytest.raises(PermissionError, match="implementation-only"):
        catalog.require_evaluation_disabled()
