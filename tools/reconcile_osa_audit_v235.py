"""Reconcile the v232–235 audit range to provider usage and endpoint receipts, read-only."""

from collections import Counter
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts"
OUT = ART / "software-benchmark-v235/audit-v232-v235-r1/reconciliation.json"
PHASES = ("232", "232-1", "232-3", "232-4", "232-5", "232-6", "232-7", "233", "234", "235")


def read(path):
    return json.loads(path.read_bytes())


def audit():
    authority = read(ROOT / "runs/software-benchmark-v234/sympy-a4-r1/authority.json")
    db = sqlite3.connect(Path(authority["ledger"]).as_uri() + "?mode=ro", uri=True)
    ledger = {}
    for slot, status, tokens, cost, provider, body in db.execute(
        "select slot,status,tokens,cost,provider_id,body from requests where slot glob 'v23[2-5]:*'"
    ):
        usage = json.loads(body)
        if (
            status != "settled"
            or provider != usage["provider_response_id"]
            or cost != usage["peak_cost_nanoyuan"]
            or tokens != usage["input_tokens"] + usage["output_tokens"]
        ):
            raise ValueError(f"Unreconciled physical request in {slot}")
        ledger.setdefault(slot, Counter()).update(
            requests=1,
            input=usage["input_tokens"],
            output=usage["output_tokens"],
            tokens=tokens,
            cost_nanoyuan=cost,
        )
    db.close()
    rows = []
    for phase in PHASES:
        (source,) = (ART / f"software-benchmark-v{phase}").glob("*/results.json")
        data = read(source)
        units = []
        if phase == "232":
            units = [(r["arm"], r["provider_usage"], r["official"]) for r in data["rows"]]
        elif phase in ("233", "234"):
            units = [(arm, r["use"], r["official"]) for arm, r in data["arms"].items()]
        elif phase == "235":
            units = [(r["label"], r, None) for r in data["rows"]]
        else:
            arm = read(source.with_name("protocol.json"))["arm"]
            units = [(arm, data["physical"], data["official"])]
        for arm, use, official in units:
            case = "SymPy-19954" if phase in ("234", "235") else "Sphinx-9591"
            slot = f"v{phase.split('-')[0]}:{case}:{arm}"
            counts = ledger.pop(slot)
            expected = [
                use.get("requests", use.get("settled", use.get("attempts"))),
                use["input"],
                use["output"],
                use.get("cost_nanoyuan", use.get("nanoyuan")),
            ]
            if [counts[k] for k in ("requests", "input", "output", "cost_nanoyuan")] != expected:
                raise ValueError(f"Run summary differs from ledger for {slot}")
            row = dict(version=phase, slot=slot, source=str(source.relative_to(ROOT)), **counts)
            if official:
                row["endpoints"] = {}
                for kind, s in official.items():
                    receipt = read(ROOT / s["receipt"])
                    if (s["status"], s["resolved"]) != (
                        receipt["status"],
                        receipt["resolved"],
                    ) or receipt["cleanup_errors"]:
                        raise ValueError(f"Unexpected {slot} {kind} receipt")
                    row["endpoints"][kind] = {k: s[k] for k in ("status", "resolved", "receipt")}
            else:
                row.update(option=use["option"], condition=use["arm"])
            rows.append(row)
    if ledger:
        raise ValueError(f"Unmapped slots: {list(ledger)}")
    total = {
        k: sum(r[k] for r in rows)
        for k in ("requests", "input", "output", "tokens", "cost_nanoyuan")
    }
    close = read(ART / "software-benchmark-v235/readiness-decisions-r1/results.json")
    start = read(ART / "software-benchmark-v232/first-pair-r1/protocol.json")[
        "prior_spend_nanoyuan"
    ]
    if (
        start + total["cost_nanoyuan"] != close["cumulative_nanoyuan"]
        or close["cash_cap_nanoyuan"] - close["cumulative_nanoyuan"]
        != close["balance_after_settlement_nanoyuan"]
    ):
        raise ValueError("Period closing balance differs")
    return dict(
        scope="v232 to v235 inclusive",
        prior_paid_nanoyuan=start,
        total=total,
        closing_paid_nanoyuan=close["cumulative_nanoyuan"],
        closing_cap_nanoyuan=close["cash_cap_nanoyuan"],
        closing_balance_nanoyuan=close["balance_after_settlement_nanoyuan"],
        new_paid_task_continuations=sum("endpoints" in r for r in rows),
        decision_only_calls=sum("option" in r for r in rows),
        rows=rows,
    )


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(audit(), indent=2, ensure_ascii=False) + "\n")
