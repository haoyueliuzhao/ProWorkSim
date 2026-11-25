"""Counterfactual acceptance of the same unedited replies; never changes prospective results."""

from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jsonschema import Draft202012Validator, ValidationError
from prepare_organization_contract_v239 import PLAN, prior
from proworksim import software_contract_explanation_transport as transport
from proworksim.software_benchmark_candidates_v054 import checked
from proworksim.storage import read_json
import json


def main():
    contract = transport.contract
    rows = {r["id"]: r for r in read_json(PLAN / "panel.json")}
    refs = {r["id"]: r for r in read_json(PLAN / "agreed-reference.json")}
    records = []
    for old in read_json(PLAN / "results.json")["records"]:
        if old["arm"] != "P1":
            continue
        row = rows[old["id"]]
        body = read_json(checked(old["response"]))
        d = json.loads(body["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"])
        schema = contract.request(row)["tools"][0]["function"]["parameters"]
        errors = [e for e in Draft202012Validator(schema).iter_errors(d)]
        r = dict(
            id=row["id"],
            repeat=old["repeat"],
            formal_valid=old["valid"],
            output_errors=[(e.json_path, e.validator) for e in errors],
            raw_choice=d.get("choice"),
            valid=False,
        )
        records.append(r)
        try:
            proposal = transport.parse(row, body)
            plan = contract.compile_decision(row, proposal)
            action = contract.dispatch(
                row, plan, contract.apply_patch(row, plan["patch"]), proposal["immediate"]
            )
            r.update(valid=True, choice=plan["disposition"], binding=action)
            if old["valid"] and (action != old["binding"] or plan["disposition"] != old["choice"]):
                raise ValueError("Previous valid result changed")
            if row["id"] in refs:
                ref = refs[row["id"]]
                labels = {contract.state(row)[v]["action"] for v in proposal["current_obligations"]}
                r.update(
                    obligation_ok=any(labels == set(s) for s in ref["obligations"]),
                    order_ok=action["action"] in ref["actions"],
                    binding_ok=action in ref["action_bindings"],
                    choice_ok=plan["disposition"] in ref["choices"],
                )
        except (ValueError, ValidationError) as e:
            if old["valid"]:
                raise
            r["error"] = str(e).splitlines()[0][:160]
    main_rows = [r for r in records if r["id"] != "gap"]
    prior.first.save(
        PLAN / "transport-replay.json",
        dict(
            records=records,
            main={
                k: sum(bool(r.get(k)) for r in main_rows)
                for k in ("valid", "obligation_ok", "order_ok", "binding_ok", "choice_ok")
            },
            raw_main_choices=dict(Counter(r["raw_choice"] for r in main_rows)),
            model_calls=0,
            worker_admission=False,
        ),
    )


if __name__ == "__main__":
    main()
