"""Build blinded, causal decision records from one member's original view and returned evidence."""

import json
from types import SimpleNamespace
from proworksim.software_context_builder_v230 import recover_observations
from proworksim.software_context_fields_v231_1 import transform
from proworksim.software_context_panel_v231 import ROOT
from proworksim.software_graph_controller_v228 import menu
from proworksim.software_anomaly_graph_v226 import tested_nodes
from proworksim.software_project_relations_v217 import identity
from proworksim.storage import read_json, atomic_write, json_bytes

PLAN = ROOT / "artifacts/software-benchmark-v236/decision-differentiation-r1"
# Last receipt is the decision boundary; a window label is not part of model input.
SOURCES = [
    ("s01", "A1", "software-benchmark-v229/dev1-balance90-r1/task-20/PREFIX", [55, 56, 64, 67]),
    ("s02", "A2", "software-benchmark-v216/target-repair6-r1/r2-task-02/ADAPT", [12]),
    ("s03", "A4", "software-benchmark-v229/dev1-balance90-r1/task-21/PREFIX", [26]),
    ("s04", "A3", "software-benchmark-v217/selection28-r1/task-04/KEEP", [40]),
    ("s05", "STABLE", "software-benchmark-v224-2/development4-r1/task-02/KEEP", [26, 30]),
    ("s06", "A1", "software-benchmark-v227/development-r1/task-00/PREFIX", [31, 39, 45, 47]),
    ("s07", "A4", "software-benchmark-v229/dev1-r1/task-01/PREFIX", [47]),
    ("s08", "A2", "software-benchmark-v216/target-repair6-r1/r2-task-04/ADAPT", [54, 56]),
    ("s09", "A3", "software-benchmark-v231-1/three-r1/SymPy-19954/T2", [57]),
    ("s10", "A1", "software-benchmark-v217/streaming-r2/task-29/KEEP", [32, 34, 40, 41]),
    ("s11", "STABLE", "software-benchmark-v228/control-r1/task-05/PREFIX", [45, 47]),
    ("s12", "A4", "software-benchmark-v217/confirmation-resume-r1/task-10/C2", [16]),
]


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json_bytes(obj))


def evidence(outcome):
    response = outcome["response"]
    res = response.get("result") or {}
    tool = outcome["decision"]["action"]
    args = outcome["decision"]["arguments"]
    item = {"operation": tool, "accepted": response["ok"], "reference": res.get("source_reference")}
    if tool in ("run_tests", "run_patch_review_tests"):
        failed, _ = tested_nodes(res)
        item.update(
            executed=res.get("executed"),
            passed=res.get("passed"),
            failed_cases=sorted(failed),
            counts=res.get("counts"),
        )
    if tool in ("replace_file", "write_file"):
        item["path"] = args.get("path")
    if tool == "integrate_patch":
        item.update(patch=args["patch_id"], conflicts=res.get("conflicts", []))
    if tool == "delivery_readiness":
        test = res.get("final_test") or {}
        item.update(
            ready=res["ready_to_submit"],
            final_version=(res.get("final_identity") or {}).get("source_reference"),
            public_test={k: test.get(k) for k in ("passed", "executed", "source_reference")},
            fixed=res["current_fixed_patch_ids"],
            packages=[
                {k: z.get(k) for k in ("task_id", "owner", "reviewer", "missing")}
                for z in res["package_chain"]["packages"]
            ],
        )
    if tool in ("begin_work", "work_readiness"):
        ready = (
            res
            if response["ok"]
            else ((response.get("error") or {}).get("rejection") or {})
            .get("context", {})
            .get("readiness", {})
        )
        item.update(task=ready.get("task_id"), ready=ready.get("ready"), gaps=ready.get("gaps", []))
    return item


def build(sid, typ, source, numbers):
    folder = ROOT / "runs" / source
    boundary = folder / "observations.json"
    if boundary.exists():
        rows = {x["ordinal"]: x["outcome"] for x in read_json(boundary)}
    else:
        boundary = folder / "boundary.json"
        rows = dict(enumerate(read_json(boundary)["outcomes"], 1))
    end = rows[numbers[-1]]
    actor = end["worker_id"]
    call = end["decision"]["model_tool_call_id"]
    for f in (*folder.glob("physical-api/*/response.json"), *folder.glob("api/*/response.json")):
        resp = read_json(f)
        if any(c["id"] == call for c in resp["choices"][0]["message"].get("tool_calls") or []):
            break
    else:
        raise ValueError((sid, "no matching native call"))
    req = read_json(f.with_name("request.json"))["payload"]
    assert req["member_id"] == actor
    wire = req["wire"]
    if "/T2" in source:
        wire = transform(wire, actor, restore=True)[0]
    obs = list(recover_observations(wire).values())[-1]
    assert obs["actor_id"] == actor
    dyn = obs["dynamic_organization"]
    work = dyn["work"]
    members = ["member_001", "member_002"]
    assert all(rows[n]["worker_id"] == actor for n in numbers)
    evid = {f"E{i}": evidence(rows[n]) for i, n in enumerate(numbers, 1)}
    last = list(evid.values())[-1]
    candidates = [k for k, w in work.items() if not w["children"]]
    if last.get("task"):
        targets = [last["task"]]
    elif last.get("packages"):
        targets = [q["task_id"] for q in last["packages"] if q["missing"]]
    elif typ == "A3":
        targets = [k for k in candidates if work[k]["owner"] == actor] or [
            k for k in candidates if work[k]["reviewer"] == actor
        ]
    else:
        targets = (
            [dyn.get("active_work", {}).get(actor)]
            if dyn.get("active_work", {}).get(actor) in candidates
            else [k for k in candidates if work[k]["owner"] == actor] or candidates
        )
    control = dyn.get("active_organization") or {}
    world = SimpleNamespace(
        dynamic=lambda: dyn,
        _task=lambda k: work[k],
        live_members=lambda: members,
        protocol=lambda: {"graph_control": {"duties": control.get("duties", {}), "versions": []}},
        _action_dynamic_status=lambda *_: dyn,
        _software=lambda: {
            "transfer_offers": {
                str(i): v
                for i, v in enumerate(obs.get("transfer_offers", []))
                if isinstance(v, dict)
            }
        },
    )
    node = dict(
        anomaly_id=sid,
        anomaly_type=typ,
        subject="withheld",
        affected_work=targets,
        evidence_refs=[
            {
                "opportunity": n,
                "command_id": rows[n]["response"]["command_id"],
                "sha256": identity(rows[n]["response"]),
            }
            for n in numbers
        ],
    )
    old = menu(world, node, actor)
    # No end-of-run budget: use the next native action boundary associated with this exact call.
    op = None
    budget = None
    for line in (folder / "runtime/experience.jsonl").open():
        e = json.loads(line)
        d = e.get("payload", {})
        if e["kind"] == "tool_call" and d["model_tool_call_id"] == call:
            op = d["opportunity_id"]
        if (
            op
            and e["kind"] == "organization_work_opportunity_v049"
            and d["opportunity_id"] == op
            and d["phase"] == "after"
        ):
            budget = d["team_budget"]["available_tokens"]
            break
    if budget is None:
        raise ValueError((sid, "missing settled budget"))
    graph = old["graph"]
    options = old["options"]
    # Respect historical single-option boundaries including STABLE/terminal review controls.
    nativefile = {
        "s01": "runs/software-benchmark-v233/repaired-osa-pair-r1/Sphinx-9591/OSA/decision.json",
        "s03": "runs/software-benchmark-v234/sympy-a4-r1/SymPy-19954/OSA/decision.json",
        "s06": "runs/software-benchmark-v228/supplement-r1/astropy-evidence-r2-launch2/W1/control-1/options.json",
        "s07": "runs/software-benchmark-v229/dev1-r1/task-01/PREFIX/candidate-bank.json",
        "s11": "runs/software-benchmark-v228/control-r1/task-05/W1/control-1/options.json",
    }.get(sid)
    if nativefile:
        frozen = read_json(ROOT / nativefile)
        frozen = frozen.get("menu", frozen)
        assert frozen["graph"]["work"] == graph["work"]
        graph, options = frozen["graph"], frozen["options"]
    scoped = {
        k: dict(
            completed=bool(work[k].get("completion_current")), authors=work[k].get("authors", [])
        )
        for k in targets
    }
    return dict(
        id=sid,
        instance=read_json(folder / "result.json")["instance_id"],
        world_instance=obs["instance_id"],
        reference_type=typ,
        observer=actor,
        targets=targets,
        graph=graph,
        options=options,
        work_status=scoped,
        evidence=evid,
        available_tokens=budget,
        provenance=dict(
            source=str(boundary.relative_to(ROOT)),
            ordinals=numbers,
            request=str(f.with_name("request.json").relative_to(ROOT)),
            commands=[rows[n]["response"]["command_id"] for n in numbers],
            receipt_hashes=[identity(rows[n]["response"]) for n in numbers],
            registered_menu=nativefile,
            checkpoint=read_json(folder / "checkpoint/manifest.json")["identity"]
            if (folder / "checkpoint/manifest.json").is_file()
            else None,
        ),
    )


if __name__ == "__main__":
    rows = [build(*source) for source in SOURCES]
    dest = PLAN / "panel.json"
    if dest.exists() and read_json(dest) != rows:
        raise ValueError("Panel changed")
    save(dest, rows)
