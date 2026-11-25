"""Same-prefix pairs using the independently frozen structured decision, including KEEP/ABSTAIN."""

import argparse
import fcntl
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_repaired_osa_pair_v233 as paired
from proworksim import software_structured_activation as activation
from run_obligation_scope_v237_1 import PLAN as DECISIONS, RUN as SOURCE, validate
from run_structured_decisions_v237 import PLAN as ORIGINAL_PANEL
from proworksim.software_handoff_evidence_v232_6 import EvidenceFollowupExecution
from proworksim.software_context_panel_v231 import DESIGN, ROOT, panel_row
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.software_benchmark_candidates_v054 import reference, checked
from proworksim.storage import read_json, json_bytes, atomic_write

PLAN = ROOT / "artifacts/software-benchmark-v238/structured-execution-r1"
RUN = ROOT / "runs/software-benchmark-v238/structured-execution-r1"
# Ordered by checkpoint availability; no conditioning on worker outcomes or model preference.
ROSTER = [("s01", 1), ("s06", 0), ("s03", 2), ("s02", None)]


def save(p, v):
    p.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(p, json_bytes(v))


def freeze():
    result = read_json(DECISIONS / "results.json")
    if not result["gate"]:
        raise ValueError("Decision admission failed")
    panel = {r["id"]: r for r in read_json(ORIGINAL_PANEL / "panel.json")}
    rows = []
    for sid, index in ROSTER:
        r = panel[sid]
        (d,) = [d for d in result["records"] if d["state"] == sid and d["arm"] == "structured"]
        item = dict(
            id=sid, index=index, instance=r["instance"], checkpoint=r["provenance"]["checkpoint"]
        )
        if index is None or not item["checkpoint"]:
            item["status"] = "missing_checkpoint"
        elif d["status"] != "valid":
            item["status"] = "inadmissible_proposal"
        else:
            state = read_json(DESIGN)["states"][index]
            if (
                r["provenance"]["checkpoint"] != state["checkpoint"]
                or r["available_tokens"] != 5_000_000 - state["shared_prefix_usage"]
            ):
                raise ValueError("Wrong frozen state")
            (response,) = (SOURCE / (sid + "-structured") / "api").glob("*/response.json")
            item.update(
                status="eligible",
                case=state["case"],
                arm_limit=r["available_tokens"],
                decision=reference(response),
                osa_tokens=d["input"] + d["output"],
                disposition=d["decision"],
            )
        rows.append(item)
    spec = dict(
        roster=rows,
        account_cap_nanoyuan=230_000_000_000,
        decision_results=reference(DECISIONS / "results.json"),
        policy="Replay the actual phase-one decision at its matching restored checkpoint and charge its original usage logically, once. Reject graph divergence. No forced change, no grading feedback, no C/N update.",
        files=[
            reference(f)
            for f in (
                Path(__file__),
                ORIGINAL_PANEL / "panel.json",
                Path(paired.episode_module.__file__),
                Path(activation.__file__),
                ROOT / "tools/run_obligation_scope_v237_1.py",
                ROOT / "src/proworksim/software_structured_policy_v237.py",
            )
        ],
    )
    dest = PLAN / "protocol.json"
    if dest.exists() and read_json(dest) != spec:
        raise ValueError("Registered state differs")
    save(dest, spec)


class StructuredExecution(EvidenceFollowupExecution):
    def decide(self, node, observer, frozen, arm):
        sid = self.binding["id"]
        row = next(r for r in read_json(ORIGINAL_PANEL / "panel.json") if r["id"] == sid)
        if (
            row["observer"] != observer
            or frozen["graph"] != row["graph"]
            or frozen["options"] != row["options"]
            or self.runtime.team_budget.snapshot()["available_tokens"] != row["available_tokens"]
        ):
            raise ValueError("Inconsistent archived graph, budget or observer")
        if arm == "KEEP":
            return super().decide(node, observer, frozen, "KEEP")
        body = read_json(checked(self.binding["decision"]))
        requested, requested_target = validate(row, body)
        d, target, evidence_hold = activation.executable_decision(row, requested, requested_target)
        native_refs = {r["command_id"]: k for k, r in frozen["evidence"].items()}
        refmap = dict(zip(row["evidence"], row["provenance"]["commands"]))
        # The actual controller accepts only previously authorized evidence, never guessed IDs.
        ids = [native_refs[refmap[k]] for k in d["decision"]["basis"]]
        if not ids:
            raise ValueError("No basis linked to the restored controller's evidence")
        debit = self.binding["osa_tokens"]
        self.native_limit -= debit
        self.runtime.team_budget.native_allocation = self.native_limit
        choice = {
            "option": target["option"],
            "evidence": ids,
            "reason": "Structured decision "
            + target["disposition"]
            + ", next action "
            + d["decision"]["next_step"]
            + ", reconsider on "
            + d["decision"]["reconsider_on"],
        }
        active = self.activate(node, observer, frozen, choice)
        rejected = active if active.get("activated") is False else None
        if rejected:
            active = self.activate(
                node,
                observer,
                frozen,
                {
                    "option": "K",
                    "evidence": ids,
                    "reason": "The proposed activation exceeds available worker opportunities; retain the current graph.",
                },
            )
        expected = row["graph"] if rejected else target["graph"]
        if active["after"] != expected:
            raise ValueError("Activated graph differs from proposal")
        if target["disposition"] == "ABSTAIN":
            self.runtime.policies[observer].conversation.send_message(
                "Existing assignments continue. Request evidence: "
                + d["decision"]["missing_evidence"]
                + ". Reconsider on "
                + d["decision"]["reconsider_on"]
                + "."
            )
        return active, dict(
            source="registered_structured_osa",
            arm=arm,
            proposal=requested,
            requested_effect=requested_target,
            effective_decision=d["decision"],
            evidence_hold=evidence_hold,
            validator="rejected" if rejected else "accepted",
            activation_rejection=rejected,
            intended_effect=target,
            osa_tokens=debit,
            new_controller_calls=0,
        )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--freeze", action="store_true")
    p.add_argument("--case")
    p.add_argument("--arm", choices=paired.ARMS)
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    if a.freeze:
        freeze()
        return
    spec = read_json(PLAN / "protocol.json")
    for f in [*spec["files"], spec["decision_results"]]:
        checked(f)
    if a.arm:
        if not a.output or a.output.name != a.arm:
            raise ValueError("Branch output mismatch")
        (binding,) = [
            i
            for i in spec["roster"]
            if i.get("case") == a.output.parent.name and i["status"] == "eligible"
        ]
        case = binding["case"]
        sub = RUN / case
        if a.output != sub / case / a.arm:
            raise ValueError("Unexpected branch destination")

        class BoundExecution(StructuredExecution):
            pass

        BoundExecution.binding = binding
        fn = paired.episode_module.episode
        clone_function(fn, {**fn.__globals__, "RUN": sub, "OrganizationExecution": BoundExecution})(
            binding["index"], a.arm, a.output, False, slot_namespace="v238", expected_case=case
        )
        return
    RUN.mkdir(parents=True, exist_ok=True)
    with (RUN / "coordinator.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for r in spec["roster"]:
            if r["status"] != "eligible":
                continue
            case = r["case"]
            sub = RUN / case
            if (sub / "completed.json").exists():
                continue
            auth = read_json(SOURCE / "authority.json")
            auth.update(scope="one v238 matched pair " + case)
            save(sub / "authority.json", auth)
            paired.reserve(
                sub / "authority.json",
                dict(
                    case=case,
                    account_cap_nanoyuan=spec["account_cap_nanoyuan"],
                    arm_limit=r["arm_limit"],
                    worst_pair_nanoyuan=2 * r["arm_limit"] * 8000,
                ),
                namespace="v238",
                block="v238:" + case,
            )
            paired.run_pair(
                sub, case, panel_row(read_json(DESIGN)["states"][r["index"]]), Path(__file__).name
            )
        save(
            RUN / "completed.json",
            {
                r["id"]: (
                    read_json(RUN / r["case"] / "completed.json")
                    if r["status"] == "eligible"
                    else r["status"]
                )
                for r in spec["roster"]
            },
        )


if __name__ == "__main__":
    main()
