"""Bind the explicit450-CNY amendment to one new resilient recovery ledger.

The original pilot ledger's400 policy is read unchanged. Only its committed
cost is carried forward; unknown reservations remain fully occupied. No import
creates a ledger or model request, and the prepared v145 ledger policy is not
mutated or reopened with an increased cap.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import software_benchmark_deepseek_api_v145 as established
from .software_benchmark_deepseek_api_v142 import _private
from .software_benchmark_candidates_v054 import checked

VERSION = "v146-resilient-recovery-explicit-cumulative450-r1"
TOTAL_CAP_NANOYUAN = 450 * 10**9


def amended_prior_cash_snapshot(path, amendment_ref):
    amendment = json.loads(checked(amendment_ref).read_text())
    if (
        amendment.get("prior_total_cap_CNY") != "400.00"
        or amendment.get("amended_total_cap_CNY") != "450.00"
        or amendment.get("additional_CNY") != "50.00"
        or amendment.get("authorization_kind") != "derived_summary_of_current_user_instruction"
        or amendment.get("does_not_release_prior_uncertain_reservations") is not True
    ):
        raise ValueError("The explicit cumulative450 budget amendment is required")
    old = established.prior_cash_snapshot(path)
    return {
        **old,
        "total_cap_nanoyuan": TOTAL_CAP_NANOYUAN,
        "available_nanoyuan": TOTAL_CAP_NANOYUAN - old["committed_prior_nanoyuan"],
        "budget_amendment": amendment_ref,
    }


def group_api(group_id, ledger_path, *, max_concurrency, panel_ref, cash_authority_ref):
    authority = json.loads(checked(cash_authority_ref).read_text())
    amendment = authority.get("budget_amendment")
    if not isinstance(amendment, dict):
        raise ValueError("The new authority must bind the explicit cumulative450 amendment")

    def snapshot(path):
        return amended_prior_cash_snapshot(path, amendment)

    expected = {
        **snapshot(authority["parent_ledger_path"]),
        "child_ledger_path": str(Path(ledger_path).resolve()),
    }
    if authority != expected:
        raise ValueError(
            "Recovery authority differs from the original committed cash plus explicit50 increment"
        )
    private = _private(established.group_api, VERSION=VERSION, prior_cash_snapshot=snapshot)
    return private(
        group_id,
        ledger_path,
        max_concurrency=max_concurrency,
        panel_ref=panel_ref,
        cash_authority_ref=cash_authority_ref,
    )
