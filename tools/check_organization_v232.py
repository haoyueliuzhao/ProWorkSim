"""Run the checked-T1 gate on archived worker inputs and the native OpenHands fixture."""

from pathlib import Path
import os
import sys
import tempfile
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_graph_execution_v230 import exercise
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.software_organization_v232 import OrganizationExecution
from proworksim.software_context_v232 import checked_context
from proworksim.software_context_builder_v230 import recover_observations, identity
from proworksim.software_context_panel_v231 import ROOT
from proworksim.storage import read_json, atomic_write, json_bytes

PLAN = ROOT / "artifacts/software-benchmark-v232/first-pair-r1"


def run():
    os.environ.update(
        LITELLM_LOCAL_MODEL_COST_MAP="True",
        OPENHANDS_SUPPRESS_BANNER="1",
        HF_HUB_OFFLINE="1",
        PYTHON_DOTENV_DISABLED="1",
    )

    def actual(backend, folder, episode, branch, condition, controller_backend):
        if condition != "T1":
            raise ValueError("New studies require T1")
        return OrganizationExecution(
            backend,
            folder,
            episode,
            branch,
            controller_backend=controller_backend,
            content_counter=len,
        )

    with tempfile.TemporaryDirectory(prefix="pws-v232-sdk-") as tmp:
        os.environ["OH_PERSISTENCE_DIR"] = str(Path(tmp) / "sdk-settings")
        sdk = clone_function(exercise, {**exercise.__globals__, "Execution": actual})(
            Path(tmp), "T1"
        )
    rows = []
    for p in sorted((ROOT / "runs/software-benchmark-v231/paired-r1").glob("*/T1")):
        ct = Counter()
        for path in (p / "telemetry/worker").glob("*/manifest.json"):
            m = read_json(path)
            raw = read_json(path.with_name("original.json"))
            out, meta = checked_context(raw, m["actor"], m["role"], m["org_graph_version"])
            if identity(recover_observations(out)) != identity(recover_observations(raw)):
                raise ValueError("Observation round trip failed")
            ct["requests"] += 1
            for r in meta["snapshots"]:
                ct[r["full"] or "delta"] += 1
        rows.append({"case": p.parent.name, "counts": ct})
    if sum(x["counts"]["requests"] for x in rows) != 89:
        raise ValueError("Archived T1 sample incomplete")
    inventory = {}
    for p in sorted(
        (ROOT / "runs").glob("software-benchmark-v22[789]/*/*/PREFIX/checkpoint/manifest.json")
    ):
        f = read_json(p)
        key = f["identity"]
        if key in inventory:
            continue
        source = p.parents[1]
        s = dict(read_json(p.with_name("state.json"))["__dict__"])
        ctrl = dict(s["control_state"]["__dict__"])
        node = dict(ctrl["node"]["__dict__"])
        inventory[key] = {
            "prefix": str(source.relative_to(ROOT)),
            "case": read_json(source / "result.json").get("instance_id"),
            "type": node["anomaly_type"],
            "subject": node["subject"],
            "remaining": 5_000_000 - f["prefix_tokens"],
        }
    atomic_write(
        PLAN / "engineering-gate.json",
        json_bytes(
            {
                "native_sdk": sdk,
                "historical_replay": rows,
                "checkpoint_inventory_v227_v229": inventory,
            }
        ),
    )


if __name__ == "__main__":
    run()
