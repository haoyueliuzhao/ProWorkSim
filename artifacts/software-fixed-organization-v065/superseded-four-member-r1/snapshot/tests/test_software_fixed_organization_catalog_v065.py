"""Six fixed treatments and no real evaluation authority, using CPU only."""
import json

import pytest

from proworksim import software_fixed_organization_v065 as catalog

MEMBERS = tuple(f"member_{index:03d}" for index in range(1, 5))
GROUPS = ("CHIEF", "SOP", "DIALOGUE", "REVIEW", "PEER", "COUNCIL")


def test_catalog_has_six_distinct_fixed_four_member_treatments():
    organizations = catalog.catalog()
    assert {row["id"] for row in organizations} == set(GROUPS)
    treatments = set()
    for row in organizations:
        assert set(row["fixed_members"]) == set(MEMBERS)
        assert set(row["roles"]) == set(MEMBERS)
        assert row["delivery_member"] == MEMBERS[0]
        assert all(a in MEMBERS and b in MEMBERS and a != b for a, b in row["communication_edges"])
        assert all(set(phase["active_members"]) <= set(MEMBERS) and phase["opportunities"] > 0
                   for phase in row["phases"])
        treatments.add(json.dumps({"edges": row["communication_edges"], "phases": row["phases"]}, sort_keys=True))
        assert catalog.validate_organization(row) == row
    assert len(treatments) == 6
    changed = catalog.get_organization("CHIEF")
    changed["roles"][MEMBERS[0]]["title"] = "replacement role"
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
