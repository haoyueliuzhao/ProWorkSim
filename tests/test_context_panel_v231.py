import json
import sqlite3
import pytest
from proworksim.software_graph_budget_v229 import WindowLedger, AdmissionStopped
from proworksim.software_context_panel_v231 import PairedLedger


def test_paired_admission_is_atomic_and_respects_other_active_holds(tmp_path):
    db = tmp_path / "test.sqlite"
    WindowLedger.create_independent(
        {"scope": "independent", "ledger": str(db), "account_cap_CNY": 40, "stage_cap_CNY": 40}
    )
    auth = tmp_path / "authority.json"
    auth.write_text(json.dumps({"cap_nanoyuan": 40 * 10**9, "ledger": str(db)}))
    ledger = PairedLedger.load(auth)
    big = {"case": "big", "remaining_per_branch": 3_847_079}
    small = {"case": "small", "remaining_per_branch": 970_203}
    with pytest.raises(AdmissionStopped):
        ledger.reserve_pair(big)
    ledger.reserve_pair(small)
    ledger.reserve_pair(small)
    ledger.admit("v231:small:T0", 970_203)
    with pytest.raises(AdmissionStopped):
        ledger.reserve_pair({"case": "competing", "remaining_per_branch": 1_550_000})
    with sqlite3.connect(db) as c:
        assert dict(c.execute("select slot,status from block_slots")) == {
            "v231:small:T0": "active",
            "v231:small:T1": "pending",
        }
    ledger.close("v231:small:T0")
    ledger.reserve_pair({"case": "competing", "remaining_per_branch": 1_550_000})
