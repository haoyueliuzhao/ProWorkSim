"""Tool-surface reproductions; usable before and after the audit fixes."""

import argparse
import json
from pathlib import Path

from proworksim.baseline import run_baseline
from proworksim.compiler import compile_world
from proworksim.designer import design
from proworksim.kernel import World
from proworksim.storage import atomic_write, digest, json_bytes
from proworksim.validation import evaluate


class Prepared(Exception):
    pass


class VariantSession:
    def __init__(self, session, citation, dependency_mode):
        self.session, self.citation, self.dependency_mode = session, citation, dependency_mode

    def observe(self):
        return self.session.observe()

    def call(self, action, **arguments):
        if action == "submit":
            raise Prepared
        if action == "write_file" and arguments.get("artifact_id") == "memo":
            memo = json.loads(arguments["content"])
            memo["citations"] = [
                {"artifact_id": "financials", "version_id": "v2", "location": self.citation}
            ]
            arguments["content"] = json.dumps(memo, ensure_ascii=False)
            if self.dependency_mode == "empty":
                arguments["dependencies"] = []
            elif self.dependency_mode == "omitted":
                arguments.pop("dependencies", None)
        return self.session.call(action, **arguments)


def reproduce(destination):
    destination = Path(destination)
    if destination.exists():
        raise ValueError("Destination must not exist")
    rows = []
    for name, citation, deps in [
        ("revenue", "values.revenue", "correct"),
        ("margin", "values.operating_margin", "correct"),
        ("empty_dependencies", "values.revenue", "empty"),
        ("omitted_dependencies", "values.revenue", "omitted"),
    ]:
        root = compile_world(design(17), destination / name)
        world = World(root)
        try:
            run_baseline(VariantSession(world.session(), citation, deps))
        except Prepared:
            pass
        assert world.session().call("submit", work_item_id="work-1")["ok"]
        assert world.session().call("wait")["ok"]
        record = evaluate(root, "work-1")[0]
        state = world.store.load()
        artifact = state["artifacts"]["memo"]
        metadata = artifact["versions"][artifact["current_version"]]
        memo_hash = digest(world.store.content(artifact))
        assert world.session().call("sheet_update", cells={"Inputs!B2": 1701})["ok"]
        after = world.store.load()["artifacts"]["memo"]
        rows.append(
            {
                "case": name,
                "passed": record["passed"],
                "evaluator_version": record["evaluator_version"],
                "failed_checks": [c["name"] for c in record["checks"] if not c["passed"]],
                "business_status": state["work_items"]["work-1"]["status"],
                "declared_dependencies": metadata["derived_from"],
                "freshness_after_model_edit": after.get("freshness"),
                "possibly_stale_after_model_edit": after["possibly_stale"],
                "memo_bytes_unchanged": digest(world.store.content(after)) == memo_hash,
            }
        )
    root = compile_world(design(17, "file"), destination / "formulas")
    session = World(root).session()
    formulas = ["=2/50%", "=2/(50%)", "=10%^2", "=(10%)^2"]
    session.call("sheet_update", cells={f"Probe!A{i}": f for i, f in enumerate(formulas, 1)})
    sheet = session.call("sheet_read", sheet="Probe")["result"]["sheets"]["Probe"]
    results = {
        "cases": rows,
        "formulas": [
            {"formula": f, "observed": sheet[f"A{i}"]["value"]} for i, f in enumerate(formulas, 1)
        ],
    }
    atomic_write(destination / "summary.json", json_bytes(results))
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("destination")
    print(json.dumps(reproduce(parser.parse_args().destination), ensure_ascii=False, indent=2))
