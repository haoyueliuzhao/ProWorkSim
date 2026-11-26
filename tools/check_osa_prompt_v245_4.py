"""Replay public decision inputs, intercepting the real OSA execution before transport."""

from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_event_pairs_v243 as event_cases
import run_full_osa_v245_4 as runner
from jsonschema import Draft202012Validator
from proworksim.software_event_orders_v243 import orders
from proworksim.storage import digest, read_json
from proworksim.software_three_graph_v240 import build


def render(row):
    w = runner.wire(row, orders(row))
    return w, json.loads(w["messages"][-1]["content"])


def main():
    root = runner.previous.ROOT
    manifest = root / "runs/software-benchmark-v055/tokenizer-r1/manifest.json"
    counter = runner.previous.M.OfficialDeepSeekCounter(
        manifest, manifest_sha256=digest(manifest.read_bytes())
    )
    counts = Counter()
    tokens = []
    archives = sorted(runner.previous.RUN.glob("*/OSA/decision-input.json"))
    assert len(archives) == 12

    class Captured(Exception):
        pass

    for archive in archives:
        record = read_json(archive)
        row = record["row"]
        row["evidence"]["E1"] = runner.evidence(
            dict(
                decision=dict(action="delivery_readiness", arguments={}),
                response=dict(ok=True, result=record["view"]),
            )
        )
        w, d = render(row)
        schema = w["tools"][0]["function"]["parameters"]
        Draft202012Validator.check_schema(schema)
        assert (
            set(d["routes"]) == set(record["routes"]) == set(schema["properties"]["route"]["enum"])
        )
        assert set(d["patches"]) == {r["option"] for r in d["routes"].values()}
        assert d["obligation_graph"]["work_root/independent_review"]["completion"] == "NOT_REQUIRED"
        assert d["obligation_graph"]["work_root/fix_tree"]["requires"] == [
            "work_root/complete_package"
        ]
        assert d["organization_graph"]["constraints"]["review_by_package"] == {
            "work_root": "optional"
        }
        counts.update({row["options"][k]["op"] for k in d["patches"]})
        size = counter.measure(w)["prompt_tokens"]
        assert size + w["max_tokens"] <= min(8192, row["available_tokens"])
        tokens.append(size)

        def capture(endpoint, payload):
            assert endpoint == "/tokenize" and payload["wire"] == w
            raise Captured()

        execution = object.__new__(runner.Execution)
        execution.record = row
        execution.trace = SimpleNamespace(branch="replay")
        execution.runtime = SimpleNamespace(team_budget=SimpleNamespace(snapshot=lambda: row))
        execution.osa = SimpleNamespace(backend=capture)
        try:
            execution.decide({}, row["observer"], row, "OSA")
        except Captured:
            pass
        else:
            raise AssertionError("Missing runtime request")

    row = deepcopy(row)
    row["probe_id"] = "work_root/independent_review"
    pkg = row["evidence"]["E1"]["packages"][0]
    for required, missing, expected in (
        (False, [], "NOT_REQUIRED"),
        (True, [], "SATISFIED"),
        (True, ["independent_current_review"], "UNSATISFIED"),
        (None, [], "UNKNOWN"),
    ):
        pkg.update(independent_review_required=required, missing=missing)
        w, d = render(row)
        assert d["obligation_graph"][row["probe_id"]]["completion"] == expected
        assert (
            expected
            in w["tools"][0]["function"]["parameters"]["properties"]["probe_completion"]["enum"]
        )

    mechanisms = Counter()
    for source in event_cases.previous.prior.sources():
        _, nodes, routes = build(source)
        if not routes:
            continue
        _, data = render({**source, "probe_id": next(iter(nodes))})
        dimensions = set()
        for order in data["optional_execution_orders"].values():
            dimensions.add(order["dimension"])
            assert order["evidence"] in source["evidence"]
            for k in order["compatible_routes"]:
                assert routes[k]["package"] == order["task"] and routes[k]["option"] in {
                    "K",
                    "WAIT",
                }
        if any(
            source["options"].get(r["option"], {}).get("op") == "diagnosis" for r in routes.values()
        ):
            dimensions.add("diagnosis")
        mechanisms.update(dimensions)
    assert {"D4", "D5", "D6", "diagnosis"} == set(mechanisms)

    print(
        json.dumps(
            dict(
                replayed=len(archives),
                selectable_in_tasks=counts,
                prompt_tokens=[min(tokens), max(tokens)],
                review_controls=4,
                historical_controls=mechanisms,
                paid_calls=0,
            ),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
